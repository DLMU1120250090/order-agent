import os

def load_prompt(filename: str) -> str:
    """
    统一的系统提示词（Prompts）加载器。
    它支持优雅的多路径降级寻找：
    1. 优先读取本重构目录下的 `diet-agent-py/prompts/` 目录（便于 Python 版本独立部署运行）。
    2. 如果找不到，为了向后兼容和最大化共用提示词模版，会向上寻找原 Java 资源文件下的 `src/main/resources/diet/prompts/`。
    """
    # 提取纯文件名，防止入参包含路径导致路径拼接失败
    base_filename = os.path.basename(filename)
    
    # 路径 1: Python 本地 prompts 文件夹
    project_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    local_path = os.path.join(project_dir, "prompts", base_filename)
    if os.path.exists(local_path):
        with open(local_path, "r", encoding="utf-8") as f:
            return f.read()
            
    # 路径 2: 原 Java 项目的 resources/diet/prompts/ 文件夹
    # 注意：Java 工程位于与 diet-agent-py 同级的 diet-agent-java 目录下
    java_path = os.path.join(os.path.dirname(project_dir), "diet-agent-java", "src", "main", "resources", "diet", "prompts", base_filename)
    if os.path.exists(java_path):
        with open(java_path, "r", encoding="utf-8") as f:
            return f.read()
            
    raise FileNotFoundError(f"提示词模板文件 {base_filename} 未能在本地 prompts/ 目录或 Java 资源目录中找到。")

