"""
范各庄矿突水事故知识图谱系统
基于 Streamlit（前端）与 Neo4j（后端）构建
功能：学生端浏览知识图谱，管理端查看访问数据
"""

import streamlit as st
import json
import os
import pandas as pd
from datetime import datetime
from neo4j import GraphDatabase
import streamlit.components.v1 as components
import hashlib
import time
from streamlit_javascript import st_javascript
from streamlit_agraph import agraph, Node, Edge, Config

# ==================== 配置区 ====================
# 1. 专属标签 (通过修改这个后缀，区分不同的人)
TARGET_LABEL = "Danmu_xujiying"

# 2. 管理员密码
ADMIN_PASSWORD = "admin888"

# 3. 数据库配置
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "wE7pV36hqNSo43mpbjTlfzE7n99NWcYABDFqUGvgSrk"

# 4. JSON文件路径
# 获取当前脚本所在的目录
current_dir = os.path.dirname(os.path.abspath(__file__))
JSON_FILE_PATH = os.path.join(current_dir, "范各庄突水事故知识图谱.json")
INTERACTIONS_FILE = os.path.join(current_dir, "interactions_log.json")  # 本地交互记录文件

# ==================== 颜色配置 ====================
CATEGORY_COLORS = {
    "事故现象": "#FF6B6B",
    "成因分析": "#4ECDC4",
    "知识原理": "#45B7D1",
    "防治措施": "#96CEB4",
    "历史意义": "#FFEAA7"
}

# ==================== Neo4j 数据库操作类 ====================
class Neo4jConnection:
    def __init__(self, uri, user, password):
        self.driver = None
        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            self.driver.verify_connectivity()
        except Exception as e:
            # Neo4j连接失败时静默处理，系统将使用纯JSON模式运行
            self.driver = None
    
    def close(self):
        if self.driver:
            self.driver.close()
    
    def execute_query(self, query, parameters=None):
        if not self.driver:
            return []
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]
    
    def execute_write(self, query, parameters=None):
        if not self.driver:
            return None
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return result.consume()

# ==================== 数据初始化 ====================
def clear_all_data(conn):
    """清除所有图形和数据（包括知识图谱和交互记录）"""
    if not conn.driver:
        return False
    
    try:
        # 清除知识图谱数据
        conn.execute_write(f"MATCH (n:{TARGET_LABEL}) DETACH DELETE n")
        
        # 清除交互记录
        conn.execute_write(f"MATCH (n:Interaction_{TARGET_LABEL}) DELETE n")
        
        return True
    except Exception as e:
        st.error(f"清除数据时出错: {e}")
        return False

def clear_local_files():
    """清除本地文件"""
    try:
        # 清除交互记录文件
        if os.path.exists(INTERACTIONS_FILE):
            os.remove(INTERACTIONS_FILE)
        
        # 清除临时图形文件
        graph_path = os.path.join(current_dir, "temp_graph.html")
        if os.path.exists(graph_path):
            os.remove(graph_path)
        
        return True
    except Exception as e:
        st.error(f"清除本地文件时出错: {e}")
        return False

def init_neo4j_data(conn, json_data):
    """将JSON数据导入Neo4j"""
    if not conn.driver:
        return False
    
    # 清除旧数据
    conn.execute_write(f"MATCH (n:{TARGET_LABEL}) DETACH DELETE n")
    
    # 创建节点
    for node in json_data.get("nodes", []):
        query = f"""
        CREATE (n:{TARGET_LABEL}:KnowledgeNode {{
            node_id: $node_id,
            label: $label,
            category: $category,
            level: $level,
            type: $type,
            properties: $properties
        }})
        """
        conn.execute_write(query, {
            "node_id": node["id"],
            "label": node["label"],
            "category": node["category"],
            "level": node["level"],
            "type": node["type"],
            "properties": json.dumps(node["properties"], ensure_ascii=False)
        })
    
    # 创建关系
    for rel in json_data.get("relationships", []):
        query = f"""
        MATCH (a:{TARGET_LABEL} {{node_id: $source}})
        MATCH (b:{TARGET_LABEL} {{node_id: $target}})
        CREATE (a)-[r:RELATES {{type: $rel_type, properties: $properties}}]->(b)
        """
        conn.execute_write(query, {
            "source": rel["source"],
            "target": rel["target"],
            "rel_type": rel.get("type", "关联"),
            "properties": json.dumps(rel.get("properties", {}), ensure_ascii=False)
        })
    
    return True

def create_new_data_warehouse():
    """创建新的空白数据仓库结构"""
    new_data = {
        "metadata": {
            "title": "新建知识图谱",
            "description": "",
            "created_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0"
        },
        "nodes": [],
        "relationships": []
    }
    return new_data

def save_json_data(data, filepath=None):
    """保存知识图谱数据到JSON文件"""
    if filepath is None:
        filepath = JSON_FILE_PATH
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        st.error(f"保存文件时出错: {e}")
        return False

def init_interaction_table(conn):
    """初始化交互记录表（在Neo4j中创建约束）"""
    if not conn.driver:
        return
    try:
        conn.execute_write(f"""
        CREATE CONSTRAINT IF NOT EXISTS FOR (n:Interaction_{TARGET_LABEL}) 
        REQUIRE n.interaction_id IS UNIQUE
        """)
    except:
        pass

def record_interaction(conn, student_id, node_id, node_label, action_type, duration=0):
    """记录学生交互行为（支持Neo4j和本地文件双模式）"""
    timestamp = datetime.now()
    
    # 尝试记录到Neo4j
    if conn.driver:
        interaction_id = f"{student_id}_{node_id}_{timestamp.strftime('%Y%m%d%H%M%S%f')}"
        query = f"""
        CREATE (i:Interaction_{TARGET_LABEL} {{
            interaction_id: $interaction_id,
            student_id: $student_id,
            node_id: $node_id,
            node_label: $node_label,
            action_type: $action_type,
            duration: $duration,
            timestamp: datetime()
        }})
        """
        conn.execute_write(query, {
            "interaction_id": interaction_id,
            "student_id": student_id,
            "node_id": node_id,
            "node_label": node_label,
            "action_type": action_type,
            "duration": duration
        })
    
    # 同时记录到本地文件（作为备份或在无Neo4j时使用）
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(INTERACTIONS_FILE), exist_ok=True)
        
        # 读取现有记录
        if os.path.exists(INTERACTIONS_FILE):
            with open(INTERACTIONS_FILE, 'r', encoding='utf-8') as f:
                interactions = json.load(f)
        else:
            interactions = []
        
        # 添加新记录
        interactions.append({
            "student_id": student_id,
            "node_id": node_id,
            "node_label": node_label,
            "action_type": action_type,
            "duration": duration,
            "timestamp": timestamp.strftime('%Y-%m-%d %H:%M:%S')
        })
        
        # 保存到文件
        with open(INTERACTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(interactions, f, ensure_ascii=False, indent=2)
    except Exception as e:
        pass  # 静默失败

def get_all_interactions(conn):
    """获取所有交互记录（优先从Neo4j，否则从本地文件）"""
    # 尝试从Neo4j获取
    if conn.driver:
        query = f"""
        MATCH (i:Interaction_{TARGET_LABEL})
        RETURN i.student_id as student_id, 
               i.node_id as node_id,
               i.node_label as node_label,
               i.action_type as action_type,
               i.duration as duration,
               toString(i.timestamp) as timestamp
        ORDER BY i.timestamp DESC
        """
        result = conn.execute_query(query)
        if result:
            return result
    
    # 从本地文件获取
    try:
        if os.path.exists(INTERACTIONS_FILE):
            with open(INTERACTIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    
    return []

def get_student_interactions(conn, student_id):
    """获取特定学生的交互记录"""
    if not conn.driver:
        return []
    query = f"""
    MATCH (i:Interaction_{TARGET_LABEL} {{student_id: $student_id}})
    RETURN i.node_id as node_id,
           i.node_label as node_label,
           i.action_type as action_type,
           i.duration as duration,
           toString(i.timestamp) as timestamp
    ORDER BY i.timestamp DESC
    """
    return conn.execute_query(query, {"student_id": student_id})

# ==================== 加载JSON数据 ====================
@st.cache_data
def load_json_data():
    """加载知识图谱JSON数据"""
    try:
        with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        st.error(f"❌ 找不到文件: {JSON_FILE_PATH}")
        return None
    except json.JSONDecodeError as e:
        st.error(f"❌ JSON解析错误: {e}")
        return None

# ==================== 创建知识图谱可视化 ====================
def create_agraph_data(json_data, selected_node=None):
    """创建 streamlit-agraph 所需的节点和边数据"""
    nodes = []
    edges = []
    
    # 添加节点
    for node in json_data.get("nodes", []):
        color = CATEGORY_COLORS.get(node["category"], "#888888")
        # 节点更小，最小10，最大22
        size = max(10, min(22, 28 - (node["level"] - 1) * 3))
        if selected_node == node["id"]:
            nodes.append(Node(
                id=node["id"],
                label=node["label"],
                size=size + 4,
                color=color,
                font={"size": 15, "color": "#222222"},
                borderWidth=3,
                borderWidthSelected=5,
                shape="dot"
            ))
        else:
            nodes.append(Node(
                id=node["id"],
                label=node["label"],
                size=size,
                color=color,
                font={"size": 13, "color": "#222222"},
                borderWidth=1,
                shape="dot"
            ))
    
    # 添加边
    for rel in json_data.get("relationships", []):
        edges.append(Edge(
            source=rel["source"],
            target=rel["target"],
            label=rel.get("type", ""),
            color="#999999",
            width=1
        ))
    
    return nodes, edges

def get_agraph_config():
    """获取 agraph 配置"""
    config = Config(
        width="100%",
        height=800,
        directed=True,
        physics=True,
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#F7A7A6",
        collapsible=False,
        node={'labelProperty': 'label'},
        link={'labelProperty': 'label', 'renderLabel': True},
        # vis-network physics参数
        physicsOptions={
            "barnesHut": {
                "gravitationalConstant": -3000,
                "centralGravity": 0.2,
                "springLength": 220,  # 路径线条更长
                "springConstant": 0.03,
                "avoidOverlap": 1
            },
            "minVelocity": 0.75
        }
    )
    return config

# ==================== 信息卡片组件 ====================
def render_info_card(node_data):
    """渲染节点信息卡片"""
    color = CATEGORY_COLORS.get(node_data["category"], "#888888")
    
    st.markdown(f"""
    <div style='
        background: #ffffff;
        border-left: 4px solid {color};
        border-radius: 12px;
        padding: 20px;
        margin: 10px 0;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    '>
        <h3 style='color: {color}; margin-bottom: 10px;'>📌 {node_data["label"]}</h3>
        <div style='display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 15px;'>
            <span style='background: {color}22; color: {color}; padding: 4px 10px; border-radius: 15px; font-size: 12px;'>
                {node_data["category"]}
            </span>
            <span style='background: #f0f0f0; color: #666; padding: 4px 10px; border-radius: 15px; font-size: 12px;'>
                {node_data["type"]}
            </span>
            <span style='background: #f0f0f0; color: #666; padding: 4px 10px; border-radius: 15px; font-size: 12px;'>
                层级 {node_data["level"]}
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # 属性详情
    st.markdown("✅ **详细信息**")
    properties = node_data.get("properties", {})
    
    if properties:
        for key, value in properties.items():
            st.markdown(f"""
            <div style='
                background: #f8f9fa;
                border-radius: 8px;
                padding: 10px 12px;
                margin: 6px 0;
                border-left: 3px solid {color};
            '>
                <span style='color: {color}; font-weight: bold; font-size: 13px;'>{key}</span>
                <p style='color: #333; margin: 4px 0 0 0; font-size: 13px; line-height: 1.5;'>{value}</p>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("暂无详细属性信息")

# ==================== 学生端页面 ====================
def student_page(conn, json_data):
    """学生端：浏览知识图谱（使用 streamlit-agraph 实现双向同步）"""
    
    # 初始化 session_state
    if "selected_node_id" not in st.session_state:
        st.session_state.selected_node_id = None
    
    # 构建节点查找字典
    nodes_dict = {node["id"]: node for node in json_data.get("nodes", [])}
    node_labels = {node["id"]: node["label"] for node in json_data.get("nodes", [])}
    label_to_id = {node["label"]: node["id"] for node in json_data.get("nodes", [])}
    
    # ========== 左侧侧边栏：登录和节点选择 ==========
    with st.sidebar:
        st.markdown("### 👤 学生登录")
        login_input = st.text_input("学号或姓名", value=st.session_state.get("login_input", ""), key="login_input_field")
        
        if st.button("确认登录", type="primary", use_container_width=True):
            if login_input:
                st.session_state.login_input = login_input
                st.session_state.student_id = login_input
                st.success(f"欢迎, {login_input}!")
            else:
                st.warning("请输入学号或姓名")
        
        if st.session_state.get("student_id"):
            st.markdown(f"✅ 已登录: **{st.session_state.student_id}**")
        
        st.markdown("---")
        
        # ========== 主区域两栏布局 ==========
        st.title("🌊 范各庄矿突水事故知识图谱")
        st.markdown("*1984年开滦范各庄矿奥陶系岩溶陷落柱特大突水灾害案例学习*")

        if not st.session_state.get("student_id"):
            st.info("💡 请在左侧输入学号和姓名登录")
            return

        # 图例
        st.markdown("##### 📊 知识分类")
        legend_html = "<div style='display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;'>"
        for cat, color in CATEGORY_COLORS.items():
            legend_html += f"<span style='background:{color}33;border:1px solid {color};border-radius:4px;padding:2px 8px;font-size:11px;color:{color};'>{cat}</span>"
        legend_html += "</div>"
        st.markdown(legend_html, unsafe_allow_html=True)

        st.markdown("---")

        # 主区域两栏：左图谱，右知识卡片
        col1, col2 = st.columns([2, 1], gap="large")
        with col1:
            st.markdown("### 🗺️ 知识图谱（点击节点右侧弹卡片）")
            nodes, edges = create_agraph_data(json_data, st.session_state.selected_node_id)
            config = get_agraph_config()
            clicked_node = agraph(nodes=nodes, edges=edges, config=config)
            # 处理图谱点击事件（同步但不刷新页面）
            if clicked_node and clicked_node != st.session_state.selected_node_id:
                st.session_state.selected_node_id = clicked_node
                if st.session_state.get("student_id") and clicked_node in node_labels:
                    record_interaction(
                        conn,
                        st.session_state.student_id,
                        clicked_node,
                        node_labels[clicked_node],
                        'view',
                        0
                    )
        with col2:
            # 右侧知识卡片弹窗
            if st.session_state.selected_node_id and st.session_state.selected_node_id in nodes_dict:
                node_data = nodes_dict[st.session_state.selected_node_id]
                render_info_card(node_data)
                st.markdown("#### 🔗 相关联系")
                related_nodes = []
                for rel in json_data.get("relationships", []):
                    if rel["source"] == st.session_state.selected_node_id:
                        target_label = node_labels.get(rel["target"], rel["target"])
                        related_nodes.append(f"➡️ **{rel.get('type', '关联')}** → {target_label}")
                    elif rel["target"] == st.session_state.selected_node_id:
                        source_label = node_labels.get(rel["source"], rel["source"])
                        related_nodes.append(f"⬅️ {source_label} **{rel.get('type', '关联')}** →")
                if related_nodes:
                    for rn in related_nodes:
                        st.markdown(rn)
                else:
                    st.info("暂无关联节点")
            else:
                st.info("💡 点击左侧图谱节点或用侧边栏选择节点查看详情")
            
            # 显示关联节点
            st.markdown("#### 🔗 相关联系")
            related_nodes = []
            for rel in json_data.get("relationships", []):
                if rel["source"] == st.session_state.selected_node_id:
                    target_label = node_labels.get(rel["target"], rel["target"])
                    related_nodes.append(f"➡️ **{rel.get('type', '关联')}** → {target_label}")
                elif rel["target"] == st.session_state.selected_node_id:
                    source_label = node_labels.get(rel["source"], rel["source"])
                    related_nodes.append(f"⬅️ {source_label} **{rel.get('type', '关联')}** →")
            
            if related_nodes:
                for rn in related_nodes:
                    st.markdown(rn)
            else:
                st.info("暂无关联节点")
        else:
            st.info("💡 点击右侧图谱节点或使用上方下拉框选择节点查看详情")
    
    # ========== 主区域 ==========
    st.title("🌊 范各庄矿突水事故知识图谱")
    st.markdown("*1984年开滦范各庄矿奥陶系岩溶陷落柱特大突水灾害案例学习*")
    
    if not st.session_state.get("student_id"):
        st.info("💡 请在左侧输入学号和姓名登录")
        return
    
    # 图例
    st.markdown("##### 📊 知识分类")
    legend_html = "<div style='display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;'>"
    for cat, color in CATEGORY_COLORS.items():
        legend_html += f"<span style='background:{color}33;border:1px solid {color};border-radius:4px;padding:2px 8px;font-size:11px;color:{color};'>{cat}</span>"
    legend_html += "</div>"
    st.markdown(legend_html, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # ========== 使用 streamlit-agraph 显示知识图谱 ==========
    st.markdown("### 🗺️ 知识图谱（点击节点可在左侧查看详情）")
    
    # 创建 agraph 数据
    nodes, edges = create_agraph_data(json_data, st.session_state.selected_node_id)
    config = get_agraph_config()
    
    # 渲染图谱并获取点击的节点
    clicked_node = agraph(nodes=nodes, edges=edges, config=config)
    
    # 处理图谱点击事件（双向同步的核心）
    if clicked_node:
        if clicked_node != st.session_state.selected_node_id:
            st.session_state.selected_node_id = clicked_node
            # 记录交互
            if st.session_state.get("student_id") and clicked_node in node_labels:
                record_interaction(
                    conn,
                    st.session_state.student_id,
                    clicked_node,
                    node_labels[clicked_node],
                    'view',
                    0
                )
            # 重新运行以更新侧边栏
            st.rerun()

# ==================== 管理端页面 ====================
def admin_page(conn, json_data):
    """管理端：查看学生访问数据"""
    st.title("📊 管理端 - 学生学习数据分析")
    
    # 显示数据来源信息
    if conn.driver:
        st.info("📡 数据来源: Neo4j 数据库")
    else:
        st.info("📁 数据来源: 本地文件 (interactions_log.json)")
    
    # 获取所有交互数据
    interactions = get_all_interactions(conn)
    
    # 调试信息
    st.caption(f"共获取到 {len(interactions)} 条记录")
    
    if not interactions:
        st.warning("暂无学生访问数据。请先在学生端浏览知识图谱，数据会自动记录。")
        
        # 显示本地文件状态
        if os.path.exists(INTERACTIONS_FILE):
            st.info(f"✅ 本地记录文件存在: {INTERACTIONS_FILE}")
            try:
                with open(INTERACTIONS_FILE, 'r', encoding='utf-8') as f:
                    local_data = json.load(f)
                    st.write(f"本地文件中有 {len(local_data)} 条记录")
                    if local_data:
                        st.dataframe(pd.DataFrame(local_data), use_container_width=True)
            except Exception as e:
                st.error(f"读取本地文件失败: {e}")
        else:
            st.warning(f"❌ 本地记录文件不存在: {INTERACTIONS_FILE}")
        
        # 提供初始化数据选项
        if conn.driver and st.button("🔄 初始化知识图谱数据到Neo4j"):
            with st.spinner("正在导入数据..."):
                if init_neo4j_data(conn, json_data):
                    init_interaction_table(conn)
                    st.success("✅ 数据初始化成功！")
                else:
                    st.error("❌ 数据初始化失败")
        return
    
    df = pd.DataFrame(interactions)
    
    # 整体统计
    st.markdown("## 📈 整体数据统计")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        total_visits = len(df)
        st.metric("总访问次数", total_visits)
    with col2:
        unique_students = df["student_id"].nunique()
        st.metric("学习学生数", unique_students)
    with col3:
        unique_nodes = df["node_id"].nunique()
        st.metric("被访问节点数", unique_nodes)
    with col4:
        avg_duration = df[df["duration"] > 0]["duration"].mean()
        st.metric("平均浏览时长(秒)", f"{avg_duration:.1f}" if pd.notna(avg_duration) else "N/A")
    
    st.divider()
    
    # 节点访问热度
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.markdown("### 🔥 节点访问热度排行")
        node_counts = df.groupby(["node_id", "node_label"]).size().reset_index(name="访问次数")
        node_counts = node_counts.sort_values("访问次数", ascending=False).head(10)
        
        st.dataframe(
            node_counts[["node_label", "访问次数"]].rename(columns={"node_label": "节点名称"}),
            use_container_width=True,
            hide_index=True
        )
    
    with col_right:
        st.markdown("### 👥 学生活跃度排行")
        student_counts = df.groupby("student_id").size().reset_index(name="访问次数")
        student_counts = student_counts.sort_values("访问次数", ascending=False).head(10)
        
        st.dataframe(
            student_counts.rename(columns={"student_id": "学号"}),
            use_container_width=True,
            hide_index=True
        )
    
    st.divider()
    
    # 类别分布
    st.markdown("### 📊 知识类别访问分布")
    
    # 合并节点类别信息
    node_categories = {node["id"]: node["category"] for node in json_data.get("nodes", [])}
    df["category"] = df["node_id"].map(node_categories)
    
    category_counts = df.groupby("category").size().reset_index(name="访问次数")
    
    # 使用柱状图
    st.bar_chart(category_counts.set_index("category")["访问次数"])
    
    st.divider()
    
    # 个人数据查询
    st.markdown("## 👤 个人学习数据查询")
    
    all_students = df["student_id"].unique().tolist()
    selected_student = st.selectbox("选择学生学号", options=all_students)
    
    if selected_student:
        student_data = df[df["student_id"] == selected_student]
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("访问节点数", student_data["node_id"].nunique())
        with col2:
            st.metric("总访问次数", len(student_data))
        with col3:
            total_duration = student_data[student_data["duration"] > 0]["duration"].sum()
            st.metric("总学习时长(秒)", int(total_duration))
        
        st.markdown("#### 📜 访问记录")
        st.dataframe(
            student_data[["node_label", "action_type", "duration", "timestamp"]].rename(columns={
                "node_label": "节点名称",
                "action_type": "操作类型",
                "duration": "浏览时长(秒)",
                "timestamp": "时间"
            }),
            use_container_width=True,
            hide_index=True
        )
        
        # 学习路径可视化
        st.markdown("#### 🛤️ 学习路径")
        path_nodes = student_data["node_label"].tolist()
        if len(path_nodes) > 1:
            path_str = " → ".join(path_nodes[:20])  # 最多显示20个
            if len(path_nodes) > 20:
                path_str += " → ..."
            st.markdown(f"```\n{path_str}\n```")
        else:
            st.info("学习路径数据不足")
    
    st.divider()
    
    # 数据管理
    st.markdown("## ⚙️ 数据管理")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 📥 数据下载")
        
        # 下载所有访问记录
        if len(df) > 0:
            # 准备下载数据
            download_df = df[["student_id", "node_id", "node_label", "action_type", "duration", "timestamp"]].copy()
            download_df.columns = ["学号", "节点ID", "节点名称", "操作类型", "浏览时长(秒)", "时间"]
            
            csv_data = download_df.to_csv(index=False, encoding='utf-8-sig')
            
            st.download_button(
                label="📊 下载全部访问记录 (CSV)",
                data=csv_data,
                file_name=f"学生访问记录_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
            
            # 下载学生汇总数据
            summary_df = df.groupby("student_id").agg({
                "node_id": "nunique",
                "node_label": "count",
                "duration": "sum"
            }).reset_index()
            summary_df.columns = ["学号", "访问节点数", "总访问次数", "总学习时长(秒)"]
            
            summary_csv = summary_df.to_csv(index=False, encoding='utf-8-sig')
            
            st.download_button(
                label="👥 下载学生汇总数据 (CSV)",
                data=summary_csv,
                file_name=f"学生学习汇总_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
            
            # 下载节点热度数据
            node_heat_df = df.groupby(["node_id", "node_label"]).size().reset_index(name="访问次数")
            node_heat_df = node_heat_df.sort_values("访问次数", ascending=False)
            node_heat_df.columns = ["节点ID", "节点名称", "访问次数"]
            
            heat_csv = node_heat_df.to_csv(index=False, encoding='utf-8-sig')
            
            st.download_button(
                label="🔥 下载节点热度数据 (CSV)",
                data=heat_csv,
                file_name=f"节点热度统计_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.info("暂无数据可下载")
    
    with col2:
        st.markdown("### 🗑️ 数据清理")
        
        st.warning("⚠️ 清除操作不可恢复，请谨慎操作！")
        
        # 使用确认机制
        confirm_clear = st.checkbox("我确认要清除所有学生学习数据")
        
        if st.button("🗑️ 清除所有学习数据", type="secondary", disabled=not confirm_clear, use_container_width=True):
            with st.spinner("正在清除数据..."):
                cleared = False
                
                # 清除Neo4j中的交互记录
                if conn.driver:
                    try:
                        conn.execute_write(f"MATCH (n:Interaction_{TARGET_LABEL}) DELETE n")
                        cleared = True
                    except Exception as e:
                        st.error(f"清除Neo4j数据失败: {e}")
                
                # 清除本地交互记录文件
                try:
                    if os.path.exists(INTERACTIONS_FILE):
                        with open(INTERACTIONS_FILE, 'w', encoding='utf-8') as f:
                            json.dump([], f)
                        cleared = True
                except Exception as e:
                    st.error(f"清除本地文件失败: {e}")
                
                if cleared:
                    st.success("✅ 所有学生学习数据已清除！")
                    st.rerun()
    
    st.divider()
    
    # 数据来源说明
    st.markdown("### 💾 数据存储说明")
    st.info("""
    **当前数据存储方式：本地文件 (interactions_log.json)**
    
    - ✅ 优点：无需额外配置，开箱即用
    - ❌ 缺点：数据存储在服务器本地，多实例部署时数据不同步
    
    **如需使用云端数据库（推荐用于生产环境）：**
    1. 配置 Neo4j 云数据库（如 Neo4j Aura）
    2. 修改代码中的 NEO4J_URI、NEO4J_USER、NEO4J_PASSWORD
    3. 云端数据库优势：数据持久化、多端同步、更安全
    """)

# ==================== 主程序入口 ====================
def main():
    st.set_page_config(
        page_title="范各庄矿突水事故知识图谱",
        page_icon="🌊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # 自定义CSS样式 - 白色主题
    st.markdown("""
    <style>
    .stApp {
        background: #ffffff;
    }
    .stSelectbox > div > div {
        background-color: #f8f9fa;
    }
    .stTextInput > div > div > input {
        background-color: #f8f9fa;
        color: #333;
    }
    .stButton > button {
        background: linear-gradient(90deg, #4ECDC4 0%, #45B7D1 100%);
        color: white;
        border: none;
        border-radius: 8px;
    }
    .stButton > button:hover {
        background: linear-gradient(90deg, #45B7D1 0%, #4ECDC4 100%);
    }
    div[data-testid="stMetricValue"] {
        font-size: 2rem;
        color: #4ECDC4;
    }
    .stSidebar {
        background-color: #f8f9fa;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 加载JSON数据
    json_data = load_json_data()
    if not json_data:
        st.error("无法加载知识图谱数据，请检查JSON文件")
        return
    
    # 连接Neo4j
    conn = Neo4jConnection(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    
    # 侧边栏导航
    st.sidebar.title("🧭 导航")
    
    page = st.sidebar.radio(
        "选择页面",
        options=["🎓 学生端", "🔐 管理端"],
        index=0
    )
    
    if page == "🎓 学生端":
        student_page(conn, json_data)
    else:
        # 管理端需要密码验证
        st.sidebar.markdown("---")
        password = st.sidebar.text_input("🔑 管理员密码", type="password")
        
        if password == ADMIN_PASSWORD:
            st.sidebar.success("✅ 验证成功")
            admin_page(conn, json_data)
        elif password:
            st.sidebar.error("❌ 密码错误")
            st.warning("请输入正确的管理员密码")
        else:
            st.info("👈 请在侧边栏输入管理员密码")
    
    # 关闭数据库连接
    conn.close()
    
    # 页脚
    st.sidebar.markdown("---")
    st.sidebar.markdown("""
    <div style='text-align: center; color: #666; font-size: 12px;'>
        <p>范各庄矿突水事故知识图谱</p>
        <p>《水文地质学》课程教学资源</p>
        <p>© 2025</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
