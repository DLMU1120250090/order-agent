-- 出行规划与预订 Agent：新增数据表 DDL
-- 对应《升级方案-出行Agent重构.md》7.1 + A2/A3/C1/C2/C3 定稿
-- 执行方式：mysql -uroot -proot test < sql/travel_tables.sql（或由建表脚本执行）

SET NAMES utf8mb4;

-- 行程主表
CREATE TABLE IF NOT EXISTS travel_trip (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id INT NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'PLANNING',
  destination VARCHAR(64) NOT NULL,
  start_date DATE NULL,
  end_date DATE NULL,
  budget VARCHAR(32) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_trip_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 候选方案表（供换一批/评估）
CREATE TABLE IF NOT EXISTS travel_plan (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  trip_id BIGINT NULL,
  score DECIMAL(6,4) NULL,
  plan_json JSON NOT NULL,
  budget_deviation DECIMAL(8,2) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_plan_trip (trip_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 订单表（状态机：DRAFT→CONFIRMED→BOOKING→PAID；改签/退票子状态）
CREATE TABLE IF NOT EXISTS travel_order (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id INT NOT NULL,
  trip_id BIGINT NULL,
  task_id VARCHAR(64) NULL,
  order_no VARCHAR(64) NOT NULL,
  supplier VARCHAR(16) NOT NULL DEFAULT 'mock',
  type VARCHAR(16) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
  idempotency_key VARCHAR(128) NOT NULL,
  price DECIMAL(10,2) NOT NULL DEFAULT 0,
  tax_fee DECIMAL(10,2) NOT NULL DEFAULT 0,
  passengers JSON NULL,
  legs JSON NULL,
  refund_rule JSON NULL,
  channel VARCHAR(16) NOT NULL DEFAULT 'web',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_order_idempotency (idempotency_key),
  UNIQUE KEY uk_order_no (order_no),
  KEY idx_order_user (user_id),
  KEY idx_order_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 后台长任务 + 定时扫描记录
CREATE TABLE IF NOT EXISTS travel_task (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id VARCHAR(64) NOT NULL,
  user_id INT NOT NULL,
  session_id VARCHAR(64) NULL,
  type VARCHAR(32) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
  params JSON NULL,
  progress INT NOT NULL DEFAULT 0,
  result JSON NULL,
  error_message VARCHAR(512) NULL,
  retry_count INT NOT NULL DEFAULT 0,
  next_run_at DATETIME NULL,
  channel VARCHAR(16) NOT NULL DEFAULT 'web',
  order_id BIGINT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_task_id (task_id),
  KEY idx_task_user (user_id),
  KEY idx_task_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- L1 用户画像（结构化，规则确定性写入）
CREATE TABLE IF NOT EXISTS user_profile (
  user_id INT PRIMARY KEY,
  home_city VARCHAR(32) NULL,
  passengers JSON NULL,
  budget_level VARCHAR(16) NULL,
  preferences JSON NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- L2 行程摘要（表 + md 双写）
CREATE TABLE IF NOT EXISTS trip_summary (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id INT NOT NULL,
  trip_id BIGINT NULL,
  summary_md TEXT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_summary_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 跨通道身份绑定
CREATE TABLE IF NOT EXISTS user_channel_binding (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id INT NOT NULL,
  channel VARCHAR(16) NOT NULL,
  channel_user_id VARCHAR(128) NOT NULL,
  bound_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_channel_user (channel, channel_user_id),
  KEY idx_binding_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 机场/车站 POI 位置表（高德 POI/地理编码缓存）
CREATE TABLE IF NOT EXISTS poi_station (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  city VARCHAR(32) NOT NULL,
  name VARCHAR(64) NOT NULL,
  kind VARCHAR(16) NOT NULL,
  lat DECIMAL(10,6) NULL,
  lng DECIMAL(10,6) NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_poi (city, name, kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 机场↔车站通勤时间缓存
CREATE TABLE IF NOT EXISTS transfer_time_cache (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  from_key VARCHAR(64) NOT NULL,
  to_key VARCHAR(64) NOT NULL,
  minutes INT NOT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_transfer (from_key, to_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 数据 API 结果缓存（内存 LRU + 落库兜底）
CREATE TABLE IF NOT EXISTS data_cache (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  cache_key VARCHAR(128) NOT NULL,
  payload JSON NULL,
  expire_at DATETIME NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_cache_key (cache_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 出行槽位字典种子数据（复用 diet_slot_option 机制）
INSERT IGNORE INTO diet_slot_option (slot_name, option_value, sort_order, enabled)
VALUES
  ('destination', '北京', 10, 1), ('destination', '上海', 11, 1), ('destination', '广州', 12, 1),
  ('destination', '深圳', 13, 1), ('destination', '成都', 14, 1), ('destination', '杭州', 15, 1),
  ('destination', '西安', 16, 1), ('destination', '重庆', 17, 1), ('destination', '南京', 18, 1),
  ('destination', '武汉', 19, 1), ('destination', '长沙', 20, 1), ('destination', '厦门', 21, 1),
  ('destination', '大连', 22, 1), ('destination', '赣州', 23, 1), ('destination', '天津', 24, 1),
  ('destination', '青岛', 25, 1), ('destination', '济南', 26, 1), ('destination', '郑州', 27, 1),
  ('destination', '沈阳', 28, 1), ('destination', '哈尔滨', 29, 1), ('destination', '昆明', 30, 1),
  ('destination', '贵阳', 31, 1), ('destination', '南宁', 32, 1), ('destination', '海口', 33, 1),
  ('destination', '三亚', 34, 1), ('destination', '乌鲁木齐', 35, 1), ('destination', '兰州', 36, 1),
  ('destination', '太原', 37, 1), ('destination', '合肥', 38, 1), ('destination', '南昌', 39, 1),
  ('destination', '石家庄', 40, 1), ('destination', '呼和浩特', 41, 1), ('destination', '银川', 42, 1),
  ('destination', '西宁', 43, 1), ('destination', '拉萨', 44, 1), ('destination', '无锡', 45, 1),
  ('destination', '宁波', 46, 1), ('destination', '温州', 47, 1), ('destination', '珠海', 48, 1),
  ('destination', '烟台', 49, 1), ('destination', '徐州', 50, 1), ('destination', '洛阳', 51, 1),
  ('origin', '北京', 60, 1), ('origin', '上海', 61, 1), ('origin', '广州', 62, 1),
  ('origin', '深圳', 63, 1), ('origin', '成都', 64, 1), ('origin', '杭州', 65, 1),
  ('origin', '西安', 66, 1), ('origin', '重庆', 67, 1), ('origin', '南京', 68, 1),
  ('origin', '武汉', 69, 1), ('origin', '大连', 70, 1), ('origin', '赣州', 71, 1),
  ('origin', '天津', 72, 1), ('origin', '青岛', 73, 1), ('origin', '济南', 74, 1),
  ('origin', '郑州', 75, 1), ('origin', '沈阳', 76, 1), ('origin', '哈尔滨', 77, 1),
  ('origin', '昆明', 78, 1), ('origin', '长沙', 79, 1), ('origin', '厦门', 80, 1),
  ('budget', '经济型', 30, 1), ('budget', '舒适型', 31, 1), ('budget', '高端型', 32, 1),
  ('travelStyle', '紧凑', 40, 1), ('travelStyle', '休闲', 41, 1), ('travelStyle', '美食', 42, 1),
  ('travelStyle', '购物', 43, 1), ('travelStyle', '亲子', 44, 1), ('travelStyle', '商务', 45, 1),
  ('transportMode', '飞机', 50, 1), ('transportMode', '高铁', 51, 1), ('transportMode', '火车', 52, 1),
  ('transportMode', '大巴', 53, 1),
  ('companion', '独自', 60, 1), ('companion', '情侣', 61, 1), ('companion', '亲子', 62, 1),
  ('companion', '商务', 63, 1);

-- 机场/车站 POI 种子数据（Mock 高德地理编码结果）
INSERT IGNORE INTO poi_station (city, name, kind, lat, lng) VALUES
  ('北京', '北京首都国际机场', 'airport', 40.0799, 116.6031),
  ('北京', '北京南站', 'station', 39.8653, 116.3786),
  ('上海', '上海虹桥国际机场', 'airport', 31.1979, 121.3363),
  ('上海', '上海虹桥站', 'station', 31.1951, 121.3201),
  ('广州', '广州白云国际机场', 'airport', 23.3924, 113.2988),
  ('广州', '广州南站', 'station', 22.9897, 113.2691),
  ('深圳', '深圳宝安国际机场', 'airport', 22.6393, 113.8108),
  ('深圳', '深圳北站', 'station', 22.6087, 114.0266),
  ('成都', '成都双流国际机场', 'airport', 30.5785, 103.9471),
  ('成都', '成都东站', 'station', 30.6301, 104.1419),
  ('杭州', '杭州萧山国际机场', 'airport', 30.2295, 120.4344),
  ('杭州', '杭州东站', 'station', 30.2906, 120.2135),
  ('西安', '西安咸阳国际机场', 'airport', 34.4471, 108.7516),
  ('西安', '西安北站', 'station', 34.3764, 108.9339),
  ('重庆', '重庆江北国际机场', 'airport', 29.7192, 106.6417),
  ('重庆', '重庆北站', 'station', 29.6085, 106.5452),
  ('南京', '南京禄口国际机场', 'airport', 31.7401, 118.8621),
  ('南京', '南京南站', 'station', 31.9702, 118.7963),
  ('武汉', '武汉天河国际机场', 'airport', 30.7838, 114.2081),
  ('武汉', '武汉站', 'station', 30.6093, 114.4231);

-- 机场↔车站通勤时间种子数据（分钟，Mock 高德 routePlan 结果，TTL 30 天）
INSERT IGNORE INTO transfer_time_cache (from_key, to_key, minutes) VALUES
  ('北京首都国际机场', '北京南站', 60),
  ('北京南站', '北京首都国际机场', 60),
  ('上海虹桥国际机场', '上海虹桥站', 20),
  ('上海虹桥站', '上海虹桥国际机场', 20),
  ('广州白云国际机场', '广州南站', 70),
  ('广州南站', '广州白云国际机场', 70),
  ('深圳宝安国际机场', '深圳北站', 50),
  ('深圳北站', '深圳宝安国际机场', 50),
  ('成都双流国际机场', '成都东站', 45),
  ('成都东站', '成都双流国际机场', 45),
  ('杭州萧山国际机场', '杭州东站', 50),
  ('杭州东站', '杭州萧山国际机场', 50),
  ('西安咸阳国际机场', '西安北站', 55),
  ('西安北站', '西安咸阳国际机场', 55),
  ('重庆江北国际机场', '重庆北站', 45),
  ('重庆北站', '重庆江北国际机场', 45),
  ('南京禄口国际机场', '南京南站', 60),
  ('南京南站', '南京禄口国际机场', 60),
  ('武汉天河国际机场', '武汉站', 55),
  ('武汉站', '武汉天河国际机场', 55);

-- 迁移：推荐反馈表增加 plan_id（方案反馈 → L1 偏好微调）
ALTER TABLE recommend_feedback ADD COLUMN plan_id VARCHAR(64) NULL AFTER item_id;
