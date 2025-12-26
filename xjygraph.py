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
from pyvis.network import Network
import streamlit.components.v1 as components
import hashlib
import time
from streamlit_javascript import st_javascript

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
def create_knowledge_graph(json_data, selected_node=None):
    """创建交互式知识图谱"""
    net = Network(height="100%", width="100%", bgcolor="#ffffff", font_color="#333333")
    net.barnes_hut(gravity=-3000, central_gravity=0.3, spring_length=200)
    
    # 添加节点
    for node in json_data.get("nodes", []):
        color = CATEGORY_COLORS.get(node["category"], "#888888")
        size = (40 - (node["level"] - 1) * 5) * 2  # 层级越高，节点越小，整体增加一倍
        
        # 如果是选中的节点，增加边框
        border_width = 5 if selected_node == node["id"] else 2
        
        net.add_node(
            node["id"],
            label=node["label"],
            color=color,
            size=size,
            title=node["label"] + " (" + node["category"] + ")",
            borderWidth=border_width,
            borderWidthSelected=5,
            font={"size": 160, "color": "#222222", "face": "Microsoft YaHei, SimHei, sans-serif", "bold": True}
        )
    
    # 添加边
    for rel in json_data.get("relationships", []):
        net.add_edge(
            rel["source"],
            rel["target"],
            title=rel.get("type", "关联"),
            label=rel.get("type", ""),
            color="#999999",
            width=1,
            arrows={"to": {"enabled": True, "scaleFactor": 0.3}},
            font={"size": 20, "color": "#555"}
        )
    
    # 配置交互选项 - 稳定后禁用物理引擎，节点可自由拖动
    net.set_options("""
    {
        "nodes": {
            "font": {
                "size": 20,
                "face": "Microsoft YaHei, SimHei, sans-serif"
            }
        },
        "edges": {
            "smooth": false,
            "width": 1,
            "color": "#999999"
        },
        "interaction": {
            "hover": true,
            "navigationButtons": false,
            "keyboard": true,
            "dragNodes": true,
            "dragView": true,
            "zoomView": true
        },
        "physics": {
            "enabled": true,
            "barnesHut": {
                "gravitationalConstant": -8000,
                "centralGravity": 0.1,
                "springLength": 300,
                "springConstant": 0.01,
                "avoidOverlap": 1
            },
            "stabilization": {
                "enabled": true,
                "iterations": 300,
                "fit": true
            }
        }
    }
    """)
    
    return net

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
    """学生端：浏览知识图谱"""
    
    # ========== 左侧侧边栏：登录和节点详情 ==========
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
        st.markdown("💡 **提示**: 点击右侧图谱中的节点查看详情")
        
        # 读取并处理localStorage中的交互记录
        if st.session_state.get("student_id"):
            try:
                interactions_js = st_javascript("""
                    var interactions = localStorage.getItem('pending_interactions');
                    if (interactions) {
                        localStorage.removeItem('pending_interactions');
                        interactions;
                    } else {
                        null;
                    }
                """, key=f"read_interactions_{int(time.time())}")
                
                if interactions_js:
                    import json as json_lib
                    try:
                        interactions_list = json_lib.loads(interactions_js)
                        for interaction in interactions_list:
                            record_interaction(
                                conn,
                                st.session_state.student_id,
                                interaction.get('node_id', ''),
                                interaction.get('node_label', ''),
                                'view',
                                0
                            )
                    except:
                        pass
            except:
                pass
    
    # ========== 主区域 ==========
    st.title("🌊 范各庄矿突水事故知识图谱")
    st.markdown("*1984年开滦范各庄矿奥陶系岩溶陷落柱特大突水灾害案例学习*")
    
    if not st.session_state.get("student_id"):
        st.info("💡 请在左侧输入学号和姓名登录")
        return
    
    # 图例（小型，放右侧）
    st.markdown("##### 📊 知识分类")
    legend_html = "<div style='display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;'>"
    for cat, color in CATEGORY_COLORS.items():
        legend_html += f"<span style='background:{color}33;border:1px solid {color};border-radius:4px;padding:2px 8px;font-size:11px;color:{color};'>{cat}</span>"
    legend_html += "</div>"
    st.markdown(legend_html, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # ========== 知识图谱（全宽显示）==========
    st.markdown("### 🗺️ 知识图谱（点击节点可在左侧查看详情）")
    
    # 获取URL参数中的选中节点，用于高亮显示
    query_params = st.query_params
    url_selected = query_params.get("selected_node", None)
    
    # 创建并显示图谱
    net = create_knowledge_graph(json_data, url_selected)
    
    # 保存并显示HTML
    graph_path = os.path.join(current_dir, "temp_graph.html")
    net.save_graph(graph_path)
    
    # 读取并嵌入HTML
    with open(graph_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    
    # 准备节点数据供 JavaScript 使用
    nodes_data = {node["id"]: node for node in json_data.get("nodes", [])}
    nodes_json = json.dumps(nodes_data, ensure_ascii=False)
    
    # 准备边的数据供高亮使用
    edges_data = json_data.get("relationships", [])
    edges_json = json.dumps(edges_data, ensure_ascii=False)
    
    # 注入点击事件处理 - 在图谱内直接显示节点详情（不刷新页面）
    click_handler = f"""
    <style>
    *, *::before, *::after {{
        box-sizing: border-box;
    }}
    html, body {{
        margin: 0 !important;
        padding: 0 !important;
        border: none !important;
        overflow: hidden !important;
        background: #ffffff !important;
    }}
    #mynetwork {{
        border: none !important;
        outline: none !important;
        box-shadow: none !important;
        margin: 0 !important;
        padding: 0 !important;
        background: #ffffff !important;
    }}
    #mynetwork > div {{
        border: none !important;
        outline: none !important;
    }}
    .vis-network {{
        border: none !important;
        outline: none !important;
    }}
    canvas {{
        border: none !important;
        outline: none !important;
    }}
    div[style*="border"] {{
        border: none !important;
    }}
    #node-detail-panel {{
        position: fixed;
        top: 20px;
        right: 20px;
        width: 380px;
        max-height: 85vh;
        background: rgba(255,255,255,0.95);
        padding: 20px 25px;
        z-index: 9999;
        overflow-y: auto;
        display: none;
        font-family: 'Microsoft YaHei', sans-serif;
        box-shadow: none !important;
    }}
    #node-detail-panel h3 {{
        margin: 0 0 15px 0;
        color: #1f77b4;
        font-size: 22px;
        padding-bottom: 10px;
        border-bottom: 2px solid #1f77b4;
    }}
    #node-detail-panel .detail-row {{
        margin: 12px 0;
        font-size: 16px;
        line-height: 1.8;
    }}
    #node-detail-panel .detail-label {{
        font-weight: bold;
        color: #333;
    }}
    #node-detail-panel .detail-value {{
        color: #555;
    }}
    #node-detail-panel .close-btn {{
        position: absolute;
        top: 15px;
        right: 20px;
        cursor: pointer;
        font-size: 24px;
        color: #999;
    }}
    #node-detail-panel .close-btn:hover {{
        color: #333;
    }}
    #node-detail-panel .relations-section {{
        margin-top: 20px;
        padding-top: 15px;
        border-top: 1px solid #ddd;
    }}
    #node-detail-panel .relations-section h4 {{
        margin: 0 0 10px 0;
        color: #666;
        font-size: 16px;
    }}
    #node-detail-panel .relation-item {{
        margin: 6px 0;
        font-size: 14px;
        color: #555;
    }}
    </style>
    
    <div id="node-detail-panel">
        <span class="close-btn" onclick="closeDetailPanel()">✕</span>
        <h3 id="detail-title">节点详情</h3>
        <div id="detail-content"></div>
        <div id="relations-content"></div>
    </div>
    
    <script>
    var nodesData = {nodes_json};
    var edgesData = {edges_json};
    var originalColors = {{}};
    var networkRef = null;
    
    function closeDetailPanel() {{
        document.getElementById('node-detail-panel').style.display = 'none';
        // 恢复所有节点和边的颜色
        if (networkRef) {{
            restoreAllColors();
        }}
    }}
    
    function restoreAllColors() {{
        if (!networkRef) return;
        var nodeUpdates = [];
        var edgeUpdates = [];
        
        // 恢复节点颜色
        for (var nodeId in originalColors.nodes) {{
            nodeUpdates.push({{id: nodeId, color: originalColors.nodes[nodeId], font: {{color: '#222222'}}}});
        }}
        // 恢复边颜色
        for (var edgeId in originalColors.edges) {{
            edgeUpdates.push({{id: edgeId, color: '#999999', font: {{color: '#555'}}}});
        }}
        
        if (nodeUpdates.length > 0) {{
            networkRef.body.data.nodes.update(nodeUpdates);
        }}
        if (edgeUpdates.length > 0) {{
            networkRef.body.data.edges.update(edgeUpdates);
        }}
        originalColors = {{nodes: {{}}, edges: {{}}}};
    }}
    
    function highlightConnected(clickedNodeId) {{
        if (!networkRef) return;
        
        // 先恢复之前的颜色
        restoreAllColors();
        
        // 找出关联的节点和边
        var connectedNodes = new Set([clickedNodeId]);
        var connectedEdgeIds = new Set();
        
        var allEdges = networkRef.body.data.edges.get();
        allEdges.forEach(function(edge) {{
            if (edge.from === clickedNodeId || edge.to === clickedNodeId) {{
                connectedNodes.add(edge.from);
                connectedNodes.add(edge.to);
                connectedEdgeIds.add(edge.id);
            }}
        }});
        
        // 保存原始颜色并设置新颜色
        var allNodes = networkRef.body.data.nodes.get();
        var nodeUpdates = [];
        var edgeUpdates = [];
        
        originalColors = {{nodes: {{}}, edges: {{}}}};
        
        allNodes.forEach(function(node) {{
            originalColors.nodes[node.id] = node.color;
            if (connectedNodes.has(node.id)) {{
                // 关联节点保持原色，可以加粗边框
                nodeUpdates.push({{id: node.id, font: {{color: '#222222'}}}});
            }} else {{
                // 非关联节点变灰
                nodeUpdates.push({{id: node.id, color: '#dddddd', font: {{color: '#bbbbbb'}}}});
            }}
        }});
        
        allEdges.forEach(function(edge) {{
            originalColors.edges[edge.id] = edge.color;
            if (connectedEdgeIds.has(edge.id)) {{
                // 关联边高亮
                edgeUpdates.push({{id: edge.id, color: '#1f77b4', font: {{color: '#1f77b4'}}}});
            }} else {{
                // 非关联边变灰
                edgeUpdates.push({{id: edge.id, color: '#eeeeee', font: {{color: '#cccccc'}}}});
            }}
        }});
        
        networkRef.body.data.nodes.update(nodeUpdates);
        networkRef.body.data.edges.update(edgeUpdates);
    }}
    
    window.onload = function() {{
        var attempts = 0;
        var maxAttempts = 20;
        
        function tryBindEvents() {{
            attempts++;
            var networkObj = null;
            
            if (typeof network !== 'undefined') {{
                networkObj = network;
            }} else if (typeof window.network !== 'undefined') {{
                networkObj = window.network;
            }}
            
            if (networkObj) {{
                networkRef = networkObj;
                
                // 稳定后禁用物理引擎
                networkObj.on('stabilized', function() {{
                    networkObj.setOptions({{physics: {{enabled: false}}}});
                }});
                
                // 点击事件 - 显示节点详情并高亮关联内容
                networkObj.on('click', function(params) {{
                    if (params.nodes && params.nodes.length > 0) {{
                        var nodeId = params.nodes[0];
                        var node = nodesData[nodeId];
                        if (node) {{
                            showNodeDetail(node, nodeId);
                            highlightConnected(nodeId);                            
                            // 记录交互到localStorage
                            try {{
                                var pending = localStorage.getItem('pending_interactions');
                                var interactions = pending ? JSON.parse(pending) : [];
                                interactions.push({{
                                    node_id: nodeId,
                                    node_label: node.label || nodeId,
                                    timestamp: new Date().toISOString()
                                }});
                                localStorage.setItem('pending_interactions', JSON.stringify(interactions));
                            }} catch(e) {{}}                        }}
                    }} else {{
                        // 点击空白处关闭面板并恢复颜色
                        closeDetailPanel();
                    }}
                }});
            }} else if (attempts < maxAttempts) {{
                setTimeout(tryBindEvents, 300);
            }}
        }}
        
        function showNodeDetail(node, nodeId) {{
            var panel = document.getElementById('node-detail-panel');
            var title = document.getElementById('detail-title');
            var content = document.getElementById('detail-content');
            var relationsContent = document.getElementById('relations-content');
            
            title.innerText = '📍 ' + (node.label || node.id);
            
            var html = '';
            
            // 显示所有属性
            if (node.category) {{
                html += '<div class="detail-row"><span class="detail-label">📂 类别：</span><span class="detail-value">' + node.category + '</span></div>';
            }}
            if (node.description) {{
                html += '<div class="detail-row"><span class="detail-label">📝 描述：</span><span class="detail-value">' + node.description + '</span></div>';
            }}
            if (node.properties) {{
                for (var key in node.properties) {{
                    if (node.properties.hasOwnProperty(key)) {{
                        var value = node.properties[key];
                        if (value && value !== '') {{
                            html += '<div class="detail-row"><span class="detail-label">🔹 ' + key + '：</span><span class="detail-value">' + value + '</span></div>';
                        }}
                    }}
                }}
            }}
            
            // 如果没有任何属性，显示基本信息
            if (html === '') {{
                html = '<div class="detail-row"><span class="detail-label">ID：</span><span class="detail-value">' + node.id + '</span></div>';
                if (node.label) {{
                    html += '<div class="detail-row"><span class="detail-label">名称：</span><span class="detail-value">' + node.label + '</span></div>';
                }}
            }}
            
            content.innerHTML = html;
            
            // 显示关联关系
            var relHtml = '<div class="relations-section"><h4>🔗 相关联系</h4>';
            var hasRelations = false;
            edgesData.forEach(function(edge) {{
                if (edge.source === nodeId) {{
                    var targetNode = nodesData[edge.target];
                    var targetLabel = targetNode ? targetNode.label : edge.target;
                    relHtml += '<div class="relation-item">➡️ <strong>' + (edge.type || '关联') + '</strong> → ' + targetLabel + '</div>';
                    hasRelations = true;
                }} else if (edge.target === nodeId) {{
                    var sourceNode = nodesData[edge.source];
                    var sourceLabel = sourceNode ? sourceNode.label : edge.source;
                    relHtml += '<div class="relation-item">⬅️ ' + sourceLabel + ' <strong>' + (edge.type || '关联') + '</strong> →</div>';
                    hasRelations = true;
                }}
            }});
            relHtml += '</div>';
            
            relationsContent.innerHTML = hasRelations ? relHtml : '';
            panel.style.display = 'block';
        }}
        
        setTimeout(tryBindEvents, 500);
    }};
    </script>
    """
    html_content = html_content.replace("</body>", click_handler + "</body>")
    
    components.html(html_content, height=1000, scrolling=False)

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
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("� 重新初始化知识图谱"):
            with st.spinner("正在重新导入数据..."):
                if init_neo4j_data(conn, json_data):
                    st.success("✅ 知识图谱数据已重新初始化")
                else:
                    st.error("❌ 初始化失败")
    
    with col2:
        if st.button("�️ 清除所有访问记录", type="secondary"):
            if conn.driver:
                conn.execute_write(f"MATCH (n:Interaction_{TARGET_LABEL}) DELETE n")
                st.success("✅ 访问记录已清除")
                st.rerun()
    
    with col3:
        if st.button("🆕 新建数据仓库", type="primary"):
            st.warning("⚠️ 此操作将清除所有现有数据！")
            if st.checkbox("我确认要清除所有数据并创建新仓库"):
                with st.spinner("正在清除数据..."):
                    # 清除Neo4j数据
                    if clear_all_data(conn):
                        st.success("✅ Neo4j数据已清除")
                    
                    # 清除本地文件
                    if clear_local_files():
                        st.success("✅ 本地文件已清除")
                    
                    # 创建新的空白数据仓库
                    new_data = create_new_data_warehouse()
                    if save_json_data(new_data):
                        st.success("✅ 新数据仓库已创建")
                        st.info("📝 请编辑 JSON 文件来添加节点和关系")
                        st.rerun()
                    else:
                        st.error("❌ 创建新数据仓库失败")

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
