import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from langchain_openai import ChatOpenAI

class Settings(BaseSettings):
    """
    系统全局配置类。
    利用 Pydantic BaseSettings 从环境变量或本地 .env 文件中加载配置参数。
    """
    # DeepSeek API 密钥，所有 LLM 交互都依赖此参数
    DEEPSEEK_API_KEY: str
    # DeepSeek OpenAI 兼容接口端点地址
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    # 主大模型名称，用于生成最终推荐理由和面向用户的口语化回答
    DIET_LLM_MAIN_MODEL: str = "deepseek-v4-flash"
    # 轻量大模型名称，用于意图分类、槽位抽取和澄清追问等基础任务，降低延迟与成本
    DIET_LLM_LIGHT_MODEL: str = "deepseek-v4-flash"
    # 异步 MySQL 数据库连接 URL（采用 aiomysql 驱动）
    DATABASE_URL: str = "mysql+aiomysql://root:root@127.0.0.1:3306/test"
    # 多轮对话历史缓存的最大轮数上限
    MAX_HISTORY_TURNS: int = 10

    # ===== 出行 Agent（Travel）配置 =====
    # 数据采集 API 密钥（阿里云市场 APPCODE / 高德 / 和风）
    TRAVEL_ALIYUN_APPCODE: str = ""
    TRAVEL_ALIYUN_APPKEY: str = ""
    TRAVEL_ALIYUN_APPSECRET: str = ""
    TRAVEL_AMAP_KEY: str = ""
    TRAVEL_AMAP_SECURITY_KEY: str = ""
    # 和风天气 JWT 认证：api-host + 私钥 PEM(base64)
    TRAVEL_QWEATHER_API_HOST: str = ""
    TRAVEL_QWEATHER_PRIVATE_KEY_B64: str = ""
    # JWT header kid = 凭据ID；payload sub = 项目ID
    TRAVEL_QWEATHER_PROJECT_ID: str = ""
    TRAVEL_QWEATHER_CREDENTIAL_ID: str = ""
    # 携程浏览器自动化持久化登录目录
    TRAVEL_CTRIP_USER_DATA_DIR: str = ""
    # 真实携程自动化开关：默认开启；优先尝试真实携程，被反爬/登录墙拦截或页面未适配时自动回退 Mock 收银台
    TRAVEL_CTRIP_REAL_ENABLED: bool = True
    # 携程国内机票频道入口
    TRAVEL_CTRIP_BASE_URL: str = "https://flights.ctrip.com/online/channel/domestic"
    # 真实携程模式默认显式打开浏览器（非无头），模拟真人操作；无头模式实测被 whaleguard 拦截
    TRAVEL_CTRIP_HEADLESS: bool = False
    # 真实携程模式浏览器通道：优先本机 Chrome（实测可过鲸盾）；可选 chrome / msedge / chromium（内置）
    TRAVEL_CTRIP_CHANNEL: str = "chrome"
    # 携程探测超时（秒）：加载页面后等待渲染，用于识别反爬/登录墙
    TRAVEL_CTRIP_PROBE_TIMEOUT: int = 20
    # 收银台二维码测试图片（相对项目根目录，如 qr_code.jpg；留空则自动生成占位二维码）
    TRAVEL_QR_TEST_IMAGE: str = ""
    # 微信桥开关（非官方协议，默认关闭）
    TRAVEL_ENABLE_WECHAT: bool = False
    # Mock 模式：外部数据 API 全部使用内置模拟数据
    TRAVEL_MOCK_MODE: bool = True
    # 价格监控净节省推送阈值（元）
    TRAVEL_PRICE_DROP_THRESHOLD: int = 50
    # 预算档位参考价（经济型,舒适型,高端型）
    TRAVEL_BUDGET_REFERENCE: str = "300,600,1000"

    # Pydantic 环境变量读取配置：指向 app 目录父级的 .env 文件，忽略多余环境变量
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def budget_tiers(self) -> dict:
        """预算档位映射：economy/comfort/premium → 参考价"""
        parts = [float(p.strip()) for p in self.TRAVEL_BUDGET_REFERENCE.split(",") if p.strip()]
        if len(parts) < 3:
            parts = [300.0, 600.0, 1000.0]
        return {"economy": parts[0], "comfort": parts[1], "premium": parts[2]}

    # ===== 钉钉通道配置 =====
    DINGTALK_APP_KEY: str = ""
    DINGTALK_APP_SECRET: str = ""
    # 原企业内部应用 AgentId（工作通知主动推送用）
    DINGTALK_AGENT_ID: str = ""
    # 新版统一应用 App ID（Stream 回调识别用）
    DINGTALK_APP_ID: str = ""
    DINGTALK_ROBOT_WEBHOOK: str = ""
    # 机器人编码（Stream/HTTP 回调消息里自带 robotCode，此配置仅作兜底）
    DINGTALK_ROBOT_CODE: str = ""

    # ===== Playwright 下单自动化（Mock 收银台，C3 定稿扩展）=====
    TRAVEL_PLAYWRIGHT_ENABLED: bool = True
    TRAVEL_PLAYWRIGHT_HEADLESS: bool = True
    TRAVEL_PLAYWRIGHT_USER_DATA_DIR: str = ""  # 空则默认 memory/playwright/ctx（持久化登录态）
    # Mock 收银台地址（演示环境指向本服务自身）
    TRAVEL_MOCK_CHECKOUT_BASE_URL: str = "http://127.0.0.1:8090"
    TRAVEL_MOCK_CHECKOUT_AUTO_PAY_SECONDS: int = 8  # Mock 页面自动模拟支付秒数（演示三层检测用）
    TRAVEL_PAYMENT_POLL_SECONDS_FAST: float = 30.0  # 第2层：前 2 分钟轮询间隔（30s）
    TRAVEL_PAYMENT_POLL_SECONDS_SLOW: float = 90.0  # 第2层：2 分钟后的轮询间隔（1~2 分钟）
    TRAVEL_PAYMENT_MONITOR_TIMEOUT: int = 900  # 三层支付检测总超时（秒，15 分钟）

    def qweather_private_key(self) -> str:
        """解码和风天气 JWT 私钥 PEM"""
        import base64
        try:
            return base64.b64decode(self.TRAVEL_QWEATHER_PRIVATE_KEY_B64).decode("utf-8")
        except Exception:
            return ""

# 实例化全局配置对象供系统各模块直接导入使用
settings = Settings()

def get_main_model() -> ChatOpenAI:
    """
    构造主 LLM 模型实例。
    设置稍高的 temperature (0.2) 以增强推荐理由和口语化应答的生成自然度。
    """
    return ChatOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        model=settings.DIET_LLM_MAIN_MODEL,
        temperature=0.2,
    )

def get_light_model() -> ChatOpenAI:
    """
    构造轻量级 LLM 模型实例。
    设置 temperature = 0.0 以确保结构化输出 (Pydantic / JSON) 和意图分类的确定性。
    """
    return ChatOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        model=settings.DIET_LLM_LIGHT_MODEL,
        temperature=0.0,
    )
