-- Create ai_task table for async AI tasks
CREATE TABLE IF NOT EXISTS `ai_task` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `task_id` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '任务ID (UUID)',
    `task_type` TINYINT NOT NULL DEFAULT 0 COMMENT '任务类型: 0-unknown, 1-translation, 2-summarization',
    `status` TINYINT NOT NULL DEFAULT 0 COMMENT '状态: 0-init, 1-before_process, 2-processing, 3-after_process, 4-finish, 5-error',
    `model` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '使用的模型',
    `user_group` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '用户组/部门',
    `params` JSON COMMENT '任务参数',
    `output` JSON COMMENT '任务输出',
    `error_message` VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '错误信息',
    `finished_at` DATETIME NOT NULL DEFAULT '1970-01-01 00:00:00' COMMENT '完成时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `deleted_at` DATETIME NOT NULL DEFAULT '1970-01-01 00:00:00' COMMENT '删除时间(软删除哨兵值1970-01-01)',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uniq_task_id` (`task_id`),
    KEY `idx_status` (`status`),
    KEY `idx_created_at` (`created_at`),
    KEY `idx_deleted_at` (`deleted_at`)
) COMMENT='异步AI任务表';
