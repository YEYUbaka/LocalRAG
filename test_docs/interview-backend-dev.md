# 后端开发面试题库

> 适用岗位：后端开发 / 全栈开发
> 更新时间：2026-06-17
> 难度标记：⭐基础 ⭐⭐进阶 ⭐⭐⭐高级

---

## 一、Web框架

### Q1: FastAPI和Flask的区别？⭐

**简答：**
> FastAPI基于ASGI、自动文档、类型检查、性能高；Flask基于WSGI、轻量灵活、生态成熟。

**详细回答：**

| 维度 | FastAPI | Flask |
|------|---------|-------|
| 协议 | ASGI（异步） | WSGI（同步） |
| 性能 | 高（接近Node.js） | 中 |
| 自动文档 | 内置Swagger/OpenAPI | 需要插件 |
| 类型检查 | 原生支持Pydantic | 不支持 |
| 学习曲线 | 中 | 低 |
| 生态 | 较新但增长快 | 成熟丰富 |

**FastAPI示例：**
```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str
    price: float

@app.post("/items/")
async def create_item(item: Item):
    return {"name": item.name, "price": item.price}
```

---

### Q2: RESTful API设计规范？⭐⭐

**简答：**
> URL用名词、HTTP方法表动作、状态码表结果、版本控制。

**详细回答：**

| 规范 | 示例 |
|------|------|
| URL用名词 | `/api/users`（不是`/getUsers`） |
| GET获取 | `GET /api/users/1` |
| POST创建 | `POST /api/users` |
| PUT更新 | `PUT /api/users/1` |
| DELETE删除 | `DELETE /api/users/1` |
| 版本控制 | `/api/v1/users` |
| 状态码 | 200成功、201创建成功、404未找到 |

---

## 二、认证与安全

### Q3: JWT认证流程？⭐⭐

**简答：**
> 用户登录后，服务器生成JWT返回客户端，客户端每次请求携带JWT，服务器验证JWT。

**详细回答：**

```
1. 用户提交用户名密码
2. 服务器验证通过，生成JWT
3. JWT = Header.Payload.Signature
4. 客户端存储JWT（localStorage/Cookie）
5. 每次请求在Header中携带：Authorization: Bearer <token>
6. 服务器验证JWT签名和有效期
```

**JWT结构：**
```json
// Header
{"alg": "HS256", "typ": "JWT"}

// Payload
{"user_id": 1, "username": "admin", "exp": 1718700000}

// Signature
HMACSHA256(base64(header) + "." + base64(payload), secret)
```

---

### Q4: SQL注入是什么？怎么防范？⭐⭐

**简答：**
> SQL注入是攻击者在输入中插入恶意SQL代码，绕过验证或执行非法操作。

**详细回答：**

**攻击示例：**
```sql
-- 原始查询
SELECT * FROM users WHERE username = 'admin' AND password = '123456'

-- 注入攻击（输入：admin' OR '1'='1）
SELECT * FROM users WHERE username = 'admin' OR '1'='1' AND password = ''
-- 结果：绕过密码验证，直接登录
```

**防范措施：**
1. **参数化查询**（最有效）：
```python
# 错误写法
query = f"SELECT * FROM users WHERE username = '{username}'"

# 正确写法
query = "SELECT * FROM users WHERE username = %s"
cursor.execute(query, (username,))
```

2. **使用ORM**：SQLAlchemy、Django ORM自动处理
3. **输入验证**：过滤特殊字符
4. **最小权限**：数据库用户只给必要权限

---

## 三、缓存

### Q5: Redis缓存穿透、击穿、雪崩？⭐⭐⭐

**简答：**
> 穿透：查不存在的数据；击穿：热点key过期；雪崩：大量key同时过期。

**详细回答：**

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 缓存穿透 | 查询不存在的数据，每次都查DB | 布隆过滤器、缓存空值 |
| 缓存击穿 | 热点key过期，大量请求打到DB | 互斥锁、永不过期 |
| 缓存雪崩 | 大量key同时过期 | 随机过期时间、多级缓存 |

---

## 四、消息队列

### Q6: 为什么使用消息队列？⭐⭐

**简答：**
> 解耦、异步、削峰。

**详细回答：**

| 场景 | 说明 | 示例 |
|------|------|------|
| 解耦 | 生产者和消费者独立 | 订单系统和库存系统 |
| 异步 | 非关键路径异步处理 | 发送邮件、短信 |
| 削峰 | 高峰期请求排队处理 | 秒杀活动 |

**常见消息队列：**
- RabbitMQ：功能丰富，适合中小规模
- Kafka：高吞吐，适合大数据场景
- RocketMQ：阿里开源，功能全面

---

## 五、速记口诀

```
RESTful：URL用名词，方法表动作，状态码表结果
JWT三部分：Header.Payload.Signature
SQL防范：参数化查询是王道
缓存三问题：穿透查空、击穿热点、雪崩同时过期
消息队列：解耦异步削峰
```

---

## 参考来源

- 后端开发面试题汇总
- JavaGuide后端面试题
