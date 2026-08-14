from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings

# 实例化异步 SQLAlchemy 数据库引擎
# pool_recycle=3600: 设置连接回收周期为 1 小时，防止 MySQL 侧因闲置过久单方面关闭连接而引发 "gone away" 异常。
# 不启用 pool_pre_ping=True 以避免与 aiomysql 驱动的 ping() 签名发生兼容性冲突。
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_recycle=3600
)

# 构造异步 Session 制造器
# class_=AsyncSession: 指定 Session 类型为异步会话
# expire_on_commit=False: 提交后不自动清除对象字段的缓存，确保读取性能并防止异步上下文外访问报错
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db():
    """
    FastAPI 路由依赖注入项：获取数据库会话。
    采用 async with 确保请求处理完后，数据库会话连接能被妥善关闭并回收到连接池中。
    """
    async with async_session_maker() as session:
        yield session

