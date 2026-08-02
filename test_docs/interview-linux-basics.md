# Linux面试题库

> 适用岗位：后端开发 / 测试开发 / 运维 / DevOps
> 更新时间：2026-06-17
> 难度标记：⭐基础 ⭐⭐进阶

---

## 一、文件与目录操作

### Q1: Linux常用文件操作命令？⭐

**简答：**
> ls（列表）、cd（切换目录）、cp（复制）、mv（移动）、rm（删除）、mkdir（创建目录）

**详细回答：**

| 命令 | 功能 | 常用参数 |
|------|------|----------|
| ls | 列出文件 | -l（详细）、-a（隐藏文件）、-h（人类可读） |
| cd | 切换目录 | cd ~（回家）、cd -（回上次）、cd ..（上一级） |
| cp | 复制 | -r（递归目录）、-i（确认覆盖） |
| mv | 移动/重命名 | -i（确认覆盖） |
| rm | 删除 | -r（递归）、-f（强制）、-i（确认） |
| mkdir | 创建目录 | -p（递归创建） |
| touch | 创建空文件 | - |
| cat | 查看文件内容 | -n（行号） |
| head/tail | 查看头/尾 | -n 10（前/后10行） |
| find | 查找文件 | -name "*.py"、-type f |

**面试口诀：**
> "ls看、cd走、cp拷、mv移、rm删、mkdir建"

---

### Q2: 文件权限怎么看？怎么改？⭐

**简答：**
> `ls -l`查看权限，`chmod`改权限，`chown`改所有者。

**详细回答：**
```
-rw-r--r-- 1 user group 1234 Jun 17 10:00 file.txt
│└┬┘└┬┘└┬┘
│ │   │   └── 其他用户权限（r-- = 4）
│ │   └────── 同组用户权限（r-- = 4）
│ └────────── 所有者权限（rw- = 6）
└──────────── 文件类型（- 普通文件，d 目录）
```

**权限数字：**
- r（读）= 4
- w（写）= 2
- x（执行）= 1

**常用命令：**
```bash
chmod 755 file.txt    # 所有者rwx，其他rx
chmod +x script.sh    # 添加执行权限
chown user:group file  # 修改所有者
```

---

### Q3: 怎么查看文件内容？⭐

**简答：**
> cat（全部）、head/tail（头/尾）、more/less（分页）、grep（搜索）

**详细回答：**

| 命令 | 适用场景 | 特点 |
|------|----------|------|
| cat | 小文件 | 一次性输出全部 |
| head | 查看开头 | 默认前10行 |
| tail | 查看末尾 | -f 实时追踪 |
| more | 大文件分页 | 只能向下翻 |
| less | 大文件分页 | 可上下翻 |
| grep | 搜索内容 | 支持正则表达式 |

**常用组合：**
```bash
tail -f app.log           # 实时查看日志
grep "ERROR" app.log      # 搜索错误日志
cat file.txt | grep "关键词"  # 管道搜索
```

---

## 二、进程管理

### Q4: 怎么查看进程？⭐

**简答：**
> ps（快照）、top（实时）、htop（增强版）

**详细回答：**
```bash
ps aux                    # 查看所有进程
ps -ef | grep python      # 查找python进程
top                       # 实时监控进程
htop                      # 增强版top
kill PID                  # 终止进程
kill -9 PID               # 强制终止
```

**ps输出字段：**
```
USER  PID  %CPU  %MEM  VSZ  RSS  TTY  STAT  START  TIME  COMMAND
```

---

### Q5: 前台和后台进程怎么切换？⭐

**简答：**
> 命令后加`&`后台运行，`Ctrl+Z`暂停，`bg`后台继续，`fg`调回前台。

**详细回答：**
```bash
./script.sh &       # 后台运行
Ctrl+Z              # 暂停当前进程
bg                  # 在后台继续运行
fg                  # 调回前台
jobs                # 查看后台任务
nohup ./script.sh & # 后台运行，退出终端不停止
```

---

## 三、网络相关

### Q6: 怎么查看网络连接？⭐

**简答：**
> netstat或ss查看端口和连接，curl测试HTTP请求。

**详细回答：**
```bash
netstat -tlnp         # 查看监听的TCP端口
ss -tlnp              # 更快的替代命令
curl http://localhost:8000  # 测试HTTP请求
ping google.com       # 测试网络连通性
traceroute google.com # 追踪路由
wget URL              # 下载文件
```

---

### Q7: 怎么查看端口被谁占用？⭐

**简答：**
> `lsof -i :端口号`或`netstat -tlnp | grep 端口号`

**详细回答：**
```bash
lsof -i :8000         # 查看8000端口被谁占用
netstat -tlnp | grep 8000  # 等效命令
fuser -k 8000/tcp     # 杀死占用8000端口的进程
```

---

## 四、系统信息

### Q8: 怎么查看系统信息？⭐

**简答：**
> uname（系统信息）、df（磁盘）、free（内存）、top（CPU）

**详细回答：**
```bash
uname -a              # 查看系统全部信息
cat /etc/os-release   # 查看发行版信息
df -h                 # 查看磁盘使用情况
free -h               # 查看内存使用情况
top                   # 查看CPU和进程信息
uptime                # 查看运行时间和负载
whoami                # 查看当前用户
```

---

## 五、Shell脚本

### Q9: Shell脚本的基本语法？⭐

**简答：**
> #!/bin/bash开头，变量赋值无空格，条件用[]，循环用for/while。

**详细回答：**
```bash
#!/bin/bash

# 变量
name="hello"
echo $name

# 条件判断
if [ $name == "hello" ]; then
    echo "match"
fi

# 循环
for i in 1 2 3; do
    echo $i
done

# 函数
greet() {
    echo "Hello, $1!"
}
greet "World"
```

---

## 六、Nginx

### Q10: Nginx是什么？常用配置？⭐⭐

**简答：**
> Nginx是高性能Web服务器，常用作反向代理、负载均衡、静态文件服务。

**详细回答：**

**常见用途：**
1. **反向代理**：将请求转发到后端服务
2. **负载均衡**：将请求分发到多个服务器
3. **静态文件服务**：提供HTML/CSS/JS文件
4. **HTTPS**：配置SSL证书

**常用配置：**
```nginx
server {
    listen 80;
    server_name example.com;

    # 反向代理
    location /api/ {
        proxy_pass http://localhost:8000/;
    }

    # 静态文件
    location / {
        root /var/www/html;
        index index.html;
    }
}
```

**常用命令：**
```bash
nginx -t              # 测试配置文件
nginx -s reload       # 重新加载配置
nginx -s stop         # 停止Nginx
```

---

## 七、速记口诀

```
文件操作：ls看、cd走、cp拷、mv移、rm删、mkdir建
权限数字：r=4, w=2, x=1
进程管理：ps看、top监、kill杀、bg后台、fg前台
网络排查：netstat看端口、curl测接口、ping测连通
```

---

## 参考来源

- Linux常用命令手册
- Linux面试题汇总
