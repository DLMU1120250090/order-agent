-- order-agent Alembic baseline schema
-- 生成时间: 2026-09-05（机器生成，勿手改）
-- 来源: mysqldump --no-data 现网 test 库 15 张 SQLModel 表 + sql/travel_tables.sql 种子数据
-- 说明: meal_item / diet_messages_backup_20260812 为遗留表，不进迁移

SET NAMES utf8mb4;

CREATE TABLE `diet_sessions` (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` bigint NOT NULL,
  `phase` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `slots` json NOT NULL,
  `last_recommendations` json NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_session_user` (`user_id`,`updated_at`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

CREATE TABLE `diet_messages` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `session_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `agent_trace_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_message_session` (`session_id`,`created_at`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=419 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

CREATE TABLE `diet_request_trace` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `trace_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `session_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` bigint NOT NULL,
  `status` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_count` int NOT NULL DEFAULT '0',
  `duration_ms` bigint DEFAULT NULL,
  `error_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `trace_json` json NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  `expected_intent` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `expected_slots` json DEFAULT NULL,
  `expected_clarify_action` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `labeled_by` bigint DEFAULT NULL,
  `labeled_at` datetime DEFAULT NULL,
  `label_note` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uk_request_trace` (`trace_id`) USING BTREE,
  KEY `idx_request_trace_session` (`session_id`,`created_at`) USING BTREE,
  KEY `idx_request_trace_user` (`user_id`,`created_at`) USING BTREE,
  KEY `idx_request_trace_status` (`status`,`created_at`) USING BTREE,
  KEY `idx_request_trace_label` (`expected_intent`,`labeled_at`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=211 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

CREATE TABLE `diet_slot_option` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `slot_name` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `option_value` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `sort_order` int NOT NULL DEFAULT '0',
  `enabled` tinyint NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uk_slot_option` (`slot_name`,`option_value`) USING BTREE,
  KEY `idx_slot_enabled` (`slot_name`,`enabled`,`sort_order`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=386 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

CREATE TABLE `recommend_feedback` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `session_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `item_id` bigint DEFAULT NULL,
  `plan_id` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `action` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `rating` int DEFAULT NULL,
  `reason` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_feedback_user` (`user_id`,`created_at`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=29 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=DYNAMIC;

CREATE TABLE `travel_trip` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `status` varchar(32) NOT NULL DEFAULT 'PLANNING',
  `destination` varchar(64) NOT NULL,
  `start_date` date DEFAULT NULL,
  `end_date` date DEFAULT NULL,
  `budget` varchar(32) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_trip_user` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=25 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `travel_plan` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `trip_id` bigint DEFAULT NULL,
  `score` decimal(6,4) DEFAULT NULL,
  `plan_json` json NOT NULL,
  `budget_deviation` decimal(8,2) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_plan_trip` (`trip_id`)
) ENGINE=InnoDB AUTO_INCREMENT=151 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `travel_order` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `trip_id` bigint DEFAULT NULL,
  `task_id` varchar(64) DEFAULT NULL,
  `order_no` varchar(64) NOT NULL,
  `supplier` varchar(16) NOT NULL DEFAULT 'mock',
  `type` varchar(16) NOT NULL,
  `status` varchar(32) NOT NULL DEFAULT 'DRAFT',
  `idempotency_key` varchar(128) NOT NULL,
  `price` decimal(10,2) NOT NULL DEFAULT '0.00',
  `tax_fee` decimal(10,2) NOT NULL DEFAULT '0.00',
  `passengers` json DEFAULT NULL,
  `legs` json DEFAULT NULL,
  `refund_rule` json DEFAULT NULL,
  `channel` varchar(16) NOT NULL DEFAULT 'web',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_order_idempotency` (`idempotency_key`),
  UNIQUE KEY `uk_order_no` (`order_no`),
  KEY `idx_order_user` (`user_id`),
  KEY `idx_order_status` (`status`)
) ENGINE=InnoDB AUTO_INCREMENT=19 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `travel_task` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` varchar(64) NOT NULL,
  `user_id` int NOT NULL,
  `session_id` varchar(64) DEFAULT NULL,
  `type` varchar(32) NOT NULL,
  `status` varchar(32) NOT NULL DEFAULT 'PENDING',
  `params` json DEFAULT NULL,
  `progress` int NOT NULL DEFAULT '0',
  `result` json DEFAULT NULL,
  `error_message` varchar(512) DEFAULT NULL,
  `retry_count` int NOT NULL DEFAULT '0',
  `next_run_at` datetime DEFAULT NULL,
  `channel` varchar(16) NOT NULL DEFAULT 'web',
  `order_id` bigint DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_task_id` (`task_id`),
  KEY `idx_task_user` (`user_id`),
  KEY `idx_task_status` (`status`)
) ENGINE=InnoDB AUTO_INCREMENT=390 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `user_profile` (
  `user_id` int NOT NULL,
  `home_city` varchar(32) DEFAULT NULL,
  `passengers` json DEFAULT NULL,
  `budget_level` varchar(16) DEFAULT NULL,
  `preferences` json DEFAULT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `trip_summary` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `trip_id` bigint DEFAULT NULL,
  `summary_md` text NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_summary_user` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `user_channel_binding` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `channel` varchar(16) NOT NULL,
  `channel_user_id` varchar(128) NOT NULL,
  `bound_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_channel_user` (`channel`,`channel_user_id`),
  KEY `idx_binding_user` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `poi_station` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `city` varchar(32) NOT NULL,
  `name` varchar(64) NOT NULL,
  `kind` varchar(16) NOT NULL,
  `lat` decimal(10,6) DEFAULT NULL,
  `lng` decimal(10,6) DEFAULT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_poi` (`city`,`name`,`kind`)
) ENGINE=InnoDB AUTO_INCREMENT=21 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `transfer_time_cache` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `from_key` varchar(64) NOT NULL,
  `to_key` varchar(64) NOT NULL,
  `minutes` int NOT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_transfer` (`from_key`,`to_key`)
) ENGINE=InnoDB AUTO_INCREMENT=21 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `data_cache` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `cache_key` varchar(128) NOT NULL,
  `payload` json DEFAULT NULL,
  `expire_at` datetime DEFAULT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_cache_key` (`cache_key`)
) ENGINE=InnoDB AUTO_INCREMENT=380 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

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
