from datetime import datetime
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    user_id = Column(Integer, nullable=True)  # nullable for migration compatibility
    created_at = Column(DateTime, default=datetime.utcnow)


class Tag(Base):
    __tablename__ = "tags"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    name       = Column(String(50), nullable=False)
    normalized_name = Column(String(50), nullable=False)
    color      = Column(String(20), default="default")
    created_at = Column(DateTime, default=datetime.utcnow)

    documents = relationship("DocumentTag", back_populates="tag", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "normalized_name",
            name="uq_tags_user_normalized_name",
        ),
    )


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id = Column(
        Integer,
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=True,
    )
    name = Column(String(100), nullable=False)
    normalized_name = Column(String(100), nullable=False)
    path_key = Column(String(220), nullable=False)
    description = Column(Text, nullable=True)
    is_system = Column(Boolean, nullable=False, default=False, server_default="0")
    is_archived = Column(Boolean, nullable=False, default=False, server_default="0")
    created_by = Column(
        SAEnum("system", "llm", "user", name="category_created_by"),
        nullable=False,
        default="system",
        server_default="system",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )

    parent = relationship("Category", remote_side=[id], back_populates="children")
    children = relationship("Category", back_populates="parent")
    documents = relationship("Document", back_populates="category")

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "path_key",
            name="uq_categories_user_path_key",
        ),
        Index(
            "ix_categories_user_parent",
            "user_id",
            "parent_id",
            "is_archived",
        ),
    )


class ClassificationEvent(Base):
    __tablename__ = "classification_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type = Column(String(32), nullable=False)
    before_state = Column(JSON, nullable=True)
    after_state = Column(JSON, nullable=True)
    document_version = Column(Integer, nullable=True)
    classification_version = Column(String(32), nullable=False)
    prompt_version = Column(String(32), nullable=True)
    model_name = Column(String(100), nullable=True)
    method = Column(String(20), nullable=True)
    confidence = Column(Float, nullable=True)
    error_code = Column(String(64), nullable=True)
    llm_call_count = Column(Integer, nullable=False, default=0, server_default="0")
    idempotency_key = Column(String(255), nullable=True)
    reverted_at = Column(DateTime, nullable=True)
    reverted_by_id = Column(
        Integer,
        ForeignKey("classification_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    document = relationship("Document", back_populates="classification_events")
    reverted_by = relationship(
        "ClassificationEvent",
        remote_side=[id],
        back_populates="reversions",
    )
    reversions = relationship("ClassificationEvent", back_populates="reverted_by")
    document_tags = relationship("DocumentTag", back_populates="classification_event")

    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_classification_events_idempotency_key",
        ),
        Index(
            "ix_classification_events_user_created",
            "user_id",
            "created_at",
            "id",
        ),
    )


class DocumentTag(Base):
    __tablename__ = "document_tags"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    tag_id      = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False)
    source = Column(
        SAEnum("llm", "user", name="document_tag_source"),
        nullable=False,
        default="user",
        server_default="user",
    )
    confidence = Column(Float, nullable=True)
    classification_event_id = Column(
        Integer,
        ForeignKey("classification_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at  = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="tags")
    tag = relationship("Tag", back_populates="documents")
    classification_event = relationship(
        "ClassificationEvent",
        back_populates="document_tags",
    )

    __table_args__ = (UniqueConstraint("document_id", "tag_id", name="uq_doc_tag"),)


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kb_id = Column(Integer, default=1, nullable=False)
    user_id = Column(Integer, nullable=True)  # nullable for migration compatibility
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_size = Column(Integer, nullable=False)
    md5_hash = Column(String(32), nullable=False)
    document_key = Column(String(64), nullable=True)
    document_version = Column(Integer, nullable=False, default=1)
    chunker_version = Column(String(32), nullable=False, default="1")
    category_id = Column(
        Integer,
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    classification_status = Column(
        SAEnum(
            "pending",
            "running",
            "completed",
            "fallback",
            "failed",
            name="classification_status",
        ),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    classification_method = Column(
        SAEnum("llm", "embedding", "user", "none", name="classification_method"),
        nullable=False,
        default="none",
        server_default="none",
    )
    classification_confidence = Column(Float, nullable=True)
    classification_version = Column(String(32), nullable=True)
    classification_error = Column(Text, nullable=True)
    classified_at = Column(DateTime, nullable=True)
    auto_summary = Column(Text, nullable=True)
    status = Column(
        SAEnum("pending", "processing", "completed", "failed", name="doc_status"),
        default="pending",
        nullable=False,
    )
    error_message = Column(Text, nullable=True)
    parsed_content = Column(Text, nullable=True)
    page_breaks = Column(JSON, nullable=True)
    chunk_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tags = relationship("DocumentTag", back_populates="document", cascade="all, delete-orphan")
    category = relationship("Category", back_populates="documents")
    classification_events = relationship(
        "ClassificationEvent",
        back_populates="document",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "kb_id", "md5_hash", name="uq_documents_scope_md5"),
        Index("ix_documents_user_category", "user_id", "category_id"),
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), default="新对话")
    user_id = Column(Integer, nullable=True)  # nullable for migration compatibility
    created_at = Column(DateTime, default=datetime.utcnow)

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(SAEnum("user", "assistant", name="msg_role"), nullable=False)
    content = Column(Text, nullable=False)
    sources = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")
