# 范各庄矿突水事故知识图谱系统

基于 Streamlit（前端）与 Neo4j（后端）构建的交互式知识图谱系统。

## � 项目仓库

GitHub: [https://github.com/chaocai1-lgtm/20251226_xjy_graph](https://github.com/chaocai1-lgtm/20251226_xjy_graph)

## �🚀 功能特点

### 学生端
- 📊 交互式知识图谱可视化
- 📝 点击节点查看详细信息卡片
- 🔗 展示知识点之间的关联关系
- 📈 自动记录学习行为（点击、浏览时长）

### 管理端
- 📊 整体数据统计（访问次数、学生数、节点热度等）
- 👥 学生活跃度排行
- 📈 知识类别访问分布
- 👤 个人学习数据查询
- 🛤️ 学习路径可视化

## 📦 安装依赖

```bash
pip install streamlit neo4j pyvis pandas
```

## ⚙️ 配置说明

在 `xjygraph.py` 文件顶部修改以下配置：

```python
# 1. 专属标签 (区分不同用户)
TARGET_LABEL = "Danmu_xujiying"

# 2. 管理员密码
ADMIN_PASSWORD = "admin888"

# 3. 数据库配置
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "your_password_here"

# 4. JSON文件路径
JSON_FILE_PATH = "范各庄突水事故知识图谱.json"
```

## 🗄️ Neo4j 配置

### 本地安装
1. 下载并安装 [Neo4j Desktop](https://neo4j.com/download/)
2. 创建新数据库
3. 启动数据库，默认端口为 7687
4. 修改配置中的 `NEO4J_PASSWORD`

### 云端 (Neo4j Aura)
如使用云端服务，修改 URI 格式为：
```python
NEO4J_URI = "neo4j+s://xxxxx.databases.neo4j.io"
```

## 🏃 运行方式

```bash
streamlit run xjygraph.py
```

## 📁 文件结构

```
知识图谱/
├── xjygraph.py                    # 主程序
├── 范各庄突水事故知识图谱.json      # 知识图谱数据
└── README.md                      # 说明文档
```

## 📚 知识图谱内容

本知识图谱围绕1984年开滦范各庄矿奥陶系岩溶陷落柱特大突水灾害展开，包含：

- **事故现象**：突水事故、高强度突水、连锁灾害、巨大损失
- **成因分析**：岩溶陷落柱、高承压含水层、底板薄弱带、地质构造控制
- **知识原理**：岩溶作用、发育条件、水系统形成、陷落柱成因、承压水动力学、突水机理
- **防治措施**：综合治理方案、排水/截流/封堵工程
- **历史意义**：技术突破、经验传承

## 🎯 教学目标

帮助学生厘清：**事故现象 → 成因分析 → 知识原理** 的逻辑关系

## 📝 使用说明

### 学生
1. 输入学号登录
2. 浏览知识图谱，点击节点查看详情
3. 系统自动记录学习行为

### 教师
1. 切换到管理端
2. 输入管理员密码 (默认: admin888)
3. 查看学生学习数据统计
4. 可查询个人学习详情

## 📄 License

MIT License
