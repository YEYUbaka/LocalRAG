# Python核心面试题库

> 适用岗位：Python开发 / 测试开发 / 数据工程 / AI应用开发
> 更新时间：2026-06-17
> 难度标记：⭐基础 ⭐⭐进阶 ⭐⭐⭐高级

---

## 一、数据类型与数据结构

### Q1: Python有哪些数据类型？⭐

**简答：**
> 六种标准类型：Number、String、List、Tuple、Dictionary、Set

**详细回答：**

| 类型 | 可变性 | 有序性 | 示例 |
|------|--------|--------|------|
| int/float | 不可变 | - | 1, 3.14 |
| str | 不可变 | 有序 | "hello" |
| list | 可变 | 有序 | [1, 2, 3] |
| tuple | 不可变 | 有序 | (1, 2, 3) |
| dict | 可变 | 无序（3.7+有序） | {"a": 1} |
| set | 可变 | 无序 | {1, 2, 3} |

---

### Q2: list和tuple的区别？⭐

**简答：**
> list可变（可增删改），tuple不可变（创建后不能修改）。

**详细回答：**
```python
# list可变
lst = [1, 2, 3]
lst[0] = 10      # ✅ 可以修改
lst.append(4)    # ✅ 可以添加

# tuple不可变
tup = (1, 2, 3)
tup[0] = 10      # ❌ 报错：TypeError
```

**追问：为什么需要tuple？**
- 代码安全：防止意外修改
- 性能：tuple比list更省内存、访问更快
- 可作为dict的key：因为不可变，可以hash

---

### Q3: 深拷贝和浅拷贝的区别？⭐⭐

**简答：**
> 浅拷贝只复制对象本身，内部元素仍是引用；深拷贝递归复制所有层级。

**详细回答：**
```python
import copy

# 浅拷贝
lst1 = [[1, 2], [3, 4]]
lst2 = copy.copy(lst1)
lst2[0][0] = 10
print(lst1[0][0])  # 10 ← 原列表也被修改了！

# 深拷贝
lst3 = copy.deepcopy(lst1)
lst3[0][0] = 20
print(lst1[0][0])  # 10 ← 原列表不受影响
```

**图解：**
```
浅拷贝：lst2 → [■, ■] → [[1,2], [3,4]]（共享内部对象）
深拷贝：lst3 → [■, ■] → [[1,2], [3,4]]（独立副本）
```

---

### Q4: is和==的区别？⭐

**简答：**
> `is`比较内存地址（是否同一对象），`==`比较值（内容是否相等）。

**详细回答：**
```python
a = [1, 2, 3]
b = [1, 2, 3]
c = a

print(a == b)   # True（值相等）
print(a is b)   # False（不是同一对象）
print(a is c)   # True（c指向a的内存地址）
```

**小整数池：**
```python
# Python对小整数[-5, 256]有缓存
a = 256
b = 256
print(a is b)   # True（同一对象）

a = 257
b = 257
print(a is b)   # False（不同对象，但CPython实现相关）
```

---

## 二、函数与作用域

### Q5: Python函数参数类型有哪些？⭐⭐

**简答：**
> 五种：位置参数、默认参数、可变参数*args、关键字参数**kwargs、命名关键字参数

**详细回答：**
```python
def func(a, b, c=10, *args, **kwargs):
    print(f"a={a}, b={b}, c={c}")
    print(f"args={args}")
    print(f"kwargs={kwargs}")

func(1, 2, 3, 4, 5, x=6, y=7)
# a=1, b=2, c=3
# args=(4, 5)
# kwargs={'x': 6, 'y': 7}
```

**参数顺序规则：**
```
位置参数 → 默认参数 → *args → 命名关键字参数 → **kwargs
```

**追问：*args和**kwargs的区别？**
- `*args`：接收位置参数，打包成tuple
- `**kwargs`：接收关键字参数，打包成dict

---

### Q6: 什么是闭包？⭐⭐

**简答：**
> 闭包是一个函数，它记住了创建时的外部变量，即使外部函数已经返回。

**详细回答：**
```python
def make_counter():
    count = 0
    def counter():
        nonlocal count  # 声明使用外部变量
        count += 1
        return count
    return counter

c = make_counter()
print(c())  # 1
print(c())  # 2
print(c())  # 3
# count变量被闭包"记住"了
```

**闭包的条件：**
1. 有内嵌函数
2. 内嵌函数引用外部函数的变量
3. 外部函数返回内嵌函数

---

### Q7: 什么是装饰器？⭐⭐

**简答：**
> 装饰器是一个函数，它接受一个函数作为参数，返回一个新函数，用于在不修改原函数的情况下添加功能。

**详细回答：**
```python
import time

def timer(func):
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        print(f"{func.__name__} 运行时间: {end-start:.2f}s")
        return result
    return wrapper

@timer  # 等价于 my_func = timer(my_func)
def my_func():
    time.sleep(1)

my_func()  # my_func 运行时间: 1.00s
```

**常见应用场景：**
- 计时器
- 日志记录
- 权限校验
- 缓存
- 重试机制

---

### Q8: 什么是生成器？yield和return的区别？⭐⭐

**简答：**
> 生成器是惰性求值的迭代器，yield每次返回一个值后暂停，下次从暂停处继续。

**详细回答：**
```python
# 生成器函数
def fibonacci():
    a, b = 0, 1
    while True:
        yield a
        a, b = b, a + b

# 使用生成器
fib = fibonacci()
print(next(fib))  # 0
print(next(fib))  # 1
print(next(fib))  # 1
print(next(fib))  # 2
```

**yield vs return：**

| 维度 | return | yield |
|------|--------|-------|
| 执行 | 函数结束 | 暂停，下次继续 |
| 返回 | 一次返回所有 | 每次返回一个 |
| 内存 | 占用全部内存 | 惰性求值，省内存 |
| 类型 | 普通函数 | 生成器函数 |

**生成器的优势：**
- 节省内存：不需要一次性加载所有数据
- 惰性计算：用到时才计算
- 可以表示无限序列

---

## 三、面向对象

### Q9: Python的面向对象三大特性？⭐

**简答：**
> 封装、继承、多态

**详细回答：**

**1. 封装**
```python
class Person:
    def __init__(self, name, age):
        self.__name = name  # 私有属性
        self.__age = age
    
    def get_name(self):  # 公开方法
        return self.__name
```

**2. 继承**
```python
class Student(Person):  # 继承Person
    def __init__(self, name, age, school):
        super().__init__(name, age)
        self.school = school
```

**3. 多态**
```python
class Dog:
    def speak(self):
        return "Woof"

class Cat:
    def speak(self):
        return "Meow"

def animal_speak(animal):
    print(animal.speak())

animal_speak(Dog())  # Woof
animal_speak(Cat())  # Meow
```

---

### Q10: __init__和__new__的区别？⭐⭐

**简答：**
> __new__创建实例（构造器），__init__初始化实例。__new__在__init__之前执行。

**详细回答：**

| 维度 | __new__ | __init__ |
|------|---------|----------|
| 作用 | 创建实例 | 初始化实例 |
| 调用时机 | 实例创建前 | 实例创建后 |
| 参数 | cls（类本身） | self（实例） |
| 返回值 | 必须返回实例 | 无返回值 |

```python
class MyClass:
    def __new__(cls, *args, **kwargs):
        print("__new__ called")
        instance = super().__new__(cls)
        return instance
    
    def __init__(self, value):
        print("__init__ called")
        self.value = value

obj = MyClass(42)
# 输出：
# __new__ called
# __init__ called
```

---

## 四、GIL与并发

### Q11: 什么是GIL？⭐⭐⭐

**简答：**
> GIL（全局解释器锁）是CPython的机制，同一时刻只有一个线程执行Python字节码，限制了多线程的并行。

**详细回答：**

**GIL的影响：**
- CPU密集型任务：多线程反而可能更慢（GIL切换开销）
- IO密集型任务：多线程有效（IO等待时释放GIL）

**解决方案：**
1. **多进程**：每个进程有独立的GIL
2. **协程**：asyncio异步编程
3. **C扩展**：numpy等库在C层面释放GIL
4. **换解释器**：Jython、PyPy等没有GIL

**面试话术：**
> "GIL是CPython的历史遗留问题，它让多线程无法利用多核CPU。对于CPU密集型任务，我会用多进程；对于IO密集型任务，多线程或协程都行。实际项目中，大部分瓶颈在IO，所以GIL影响没那么大。"

---

### Q12: 多线程、多进程、协程的区别？⭐⭐

**简答：**
> 多进程独立内存适合CPU密集；多线程共享内存适合IO密集；协程更轻量，单线程实现并发。

**详细回答：**

| 维度 | 多进程 | 多线程 | 协程 |
|------|--------|--------|------|
| 内存 | 独立内存空间 | 共享内存空间 | 共享内存 |
| 创建开销 | 大 | 中 | 小 |
| 切换开销 | 大（内核态） | 中 | 小（用户态） |
| 数据共享 | 需要IPC | 直接共享 | 直接共享 |
| GIL影响 | 无（独立GIL） | 有 | 无 |
| 适用场景 | CPU密集 | IO密集 | IO密集 |

---

## 五、其他高频题

### Q13: lambda函数是什么？⭐

**简答：**
> lambda是匿名函数，只能有一个表达式，返回值就是表达式结果。

**详细回答：**
```python
# 普通函数
def add(x, y):
    return x + y

# lambda函数
add = lambda x, y: x + y

# 常用场景
sorted([3, 1, 2], key=lambda x: x)  # [1, 2, 3]
map(lambda x: x**2, [1, 2, 3])      # [1, 4, 9]
filter(lambda x: x > 1, [1, 2, 3])  # [2, 3]
```

---

### Q14: Python的内存管理机制？⭐⭐

**简答：**
> 引用计数为主，标记清除和分代回收为辅。

**详细回答：**
1. **引用计数**：每个对象有引用计数，为0时立即释放
2. **标记清除**：处理循环引用
3. **分代回收**：新对象在年轻代，存活久的对象移到老年代

**追问：什么是循环引用？**
```python
a = []
b = [a]
a.append(b)
# a和b互相引用，引用计数永远不为0
# 需要标记清除来处理
```

---

### Q15: 解释型和编译型语言的区别？⭐

**简答：**
> 编译型先编译再执行，速度快但跨平台差；解释型逐行翻译执行，速度慢但跨平台好。

**详细回答：**

| 维度 | 编译型 | 解释型 |
|------|--------|--------|
| 执行方式 | 先编译成机器码 | 逐行解释执行 |
| 运行速度 | 快 | 慢 |
| 跨平台 | 差 | 好 |
| 代表语言 | C、C++、Go | Python、JavaScript、Ruby |
| 典型应用 | 系统软件、游戏 | Web开发、脚本 |

**Python是解释型但有编译：**
> Python代码先编译成字节码（.pyc），再由Python虚拟机解释执行。

---

## 六、速记口诀

```
数据类型六种：数字符串列表，元组字典集合
参数顺序：位默可命关（位置→默认→*args→命名关键字→**kwargs）
深浅拷贝：浅拷贝只复制外层，深拷贝递归复制全部
is和==：is比地址，==比值
装饰器：函数包函数，功能不修改
GIL：一个锁锁住多线程，CPU密集用多进程
```

---

## 参考来源

- 测试秋招八股文集锦——Python高频考点（牛客网）
- Python面试题大全
- Python核心编程面试题
