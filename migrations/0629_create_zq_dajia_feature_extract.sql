-- --------------------------------------------------
-- 打架斗殴语义特征提取目标表 (jcgkzx_monitor.zq_dajia_feature_extract)
--
-- 数据流:
--   源表 ywdata.zq_kshddpt_dsjfx_jq
--     打架斗殴口径: 叶子代码 neworicharasubclass(原始) 或 newcharasubclass(确认)
--     命中 jcgkzx_monitor.case_type_config 中 leixing='打架斗殴' 的 newcharasubclass_list
--     -> clean_replies 清洗 replies(处警情况)
--     -> 锐智 ayenaspring-pro-001 语义抽取特征
--     -> 本表 (一条警情一行, caseno 唯一)
--
-- 字段分三层:
--   1) 基础字段:与 ywdata.zq_kshddpt_dsjfx_jq 共有(对齐参考表 zq_jingqing_number_extract)
--   2) 清洗字段:clean_replies 产出
--   3) 特征字段:锐智语义抽取 + 代码按 calltime 推导的时段维度
--
-- 增量策略: MAX(source_updatetime) 水位线 - lookback 分钟 buffer
-- 在内网执行本 SQL 建表。重置请手动 DROP。
-- --------------------------------------------------

CREATE SCHEMA IF NOT EXISTS jcgkzx_monitor;

-- DROP TABLE IF EXISTS jcgkzx_monitor.zq_dajia_feature_extract;
CREATE TABLE IF NOT EXISTS jcgkzx_monitor.zq_dajia_feature_extract (
    id BIGSERIAL PRIMARY KEY,
    caseno VARCHAR(100) NOT NULL,                           -- 警情编号(业务主键)

    -- ============ 1. 基础字段(源表 zq_kshddpt_dsjfx_jq 共有) ============
    source_updatetime TIMESTAMP,                            -- 源表数据更新时间(增量水位线依据)
    calltime TIMESTAMP,                                     -- 报警时间
    cmdid VARCHAR(50),                                      -- 地区编码
    cmdname VARCHAR(100),                                   -- 地区名称
    callerphone VARCHAR(50),                                -- 报警电话
    callername VARCHAR(100),                                -- 报警人
    occuraddress VARCHAR(500),                              -- 警情地址(地点-警情地址 提取源)
    casecontents TEXT,                                      -- 报警内容
    replies TEXT,                                           -- 处警情况(其余特征提取源, 经清洗后入模)
    dutydeptno VARCHAR(50),                                 -- 管辖单位代码
    dutydeptname VARCHAR(200),                              -- 管辖单位名称
    callway VARCHAR(100),                                   -- 报警方式
    newrecvtype VARCHAR(50),                                -- 警情来源代码
    newrecvtypename VARCHAR(100),                           -- 警情来源名称
    neworicharacategory VARCHAR(50),                        -- 原始警情大类代码
    neworicharacategoryname VARCHAR(100),                   -- 原始警情大类名称
    neworicharatype VARCHAR(50),                            -- 原始警情二类代码
    neworicharatypename VARCHAR(100),                       -- 原始警情二类名称
    neworicharasubcategory VARCHAR(50),                     -- 原始警情三类代码
    neworicharasubcategoryname VARCHAR(100),                -- 原始警情三类名称
    neworicharasubclass VARCHAR(50),                        -- 原始警情四类代码(打架斗殴过滤命中列之一)
    neworicharasubclassname VARCHAR(100),                   -- 原始警情四类名称
    newcharacategory VARCHAR(50),                           -- 确认警情大类代码
    newcharacategoryname VARCHAR(100),                      -- 确认警情大类名称
    newcharatype VARCHAR(50),                               -- 确认警情二类代码
    newcharatypename VARCHAR(100),                          -- 确认警情二类名称
    newcharasubcategory VARCHAR(50),                        -- 确认警情三类代码
    newcharasubcategoryname VARCHAR(100),                   -- 确认警情三类名称
    newcharasubclass VARCHAR(50),                           -- 确认警情四类代码(打架斗殴过滤命中列之一)
    newcharasubclassname VARCHAR(100),                      -- 确认警情四类名称
    lngofcriterion VARCHAR(50),                             -- 警情经度
    latofcriterion VARCHAR(50),                             -- 警情纬度
    casemark VARCHAR(200),                                  -- 警情标签
    casemarkno VARCHAR(200),                                -- 警情标签代码
    casemarkok VARCHAR(200),                                -- 确认警情标签
    casemarkokno VARCHAR(200),                              -- 确认警情标签代码
    standardcaseno VARCHAR(100),                            -- 部警情编号

    -- ============ 2. 清洗字段(clean_replies 产出) ============
    cjqk_cleaned TEXT,                                      -- 清洗后的处警情况(去掉指挥流水头)
    feedback_source VARCHAR(20),                            -- 来源: 结警反馈/过程反馈/不出警原因/自接警情/补充/无
    disposition_result VARCHAR(200),                        -- 处理结果(从"处理结果:"提取)
    data_quality_flag VARCHAR(20),                          -- 质量标记: 有效案情/低质量/无效警情/外市转办/无有效信息

    -- ============ 3a. 必需特征(锐智语义抽取) ============
    is_armed VARCHAR(10),                                   -- 1.是否持械: 是/否/未载明
    weapon_type VARCHAR(50),                                -- 2.持械类型: 刀具/棍棒/砖石/酒瓶/钝器/徒手/其他/未持械/未载明
    is_drunk VARCHAR(10),                                   -- 3.是否饮酒: 是/否/未载明
    brawl_reason VARCHAR(500),                              -- 4.打架原因(原文简述)
    brawl_reason_category VARCHAR(40),                      -- 5.打架原因分类(枚举见下)
    is_group_fight VARCHAR(10),                             -- 6.是否多人(打人者3人及以上): 是/否/未载明
    location_address VARCHAR(500),                          -- 7.地点(取自 occuraddress)
    location_address_category VARCHAR(40),                  -- 8.地点分类(警情地址)(枚举见下)
    location_replies VARCHAR(500),                          -- 9.地点(取自 处警情况)
    location_replies_category VARCHAR(40),                  -- 10.地点分类(处警情况)(枚举见下)

    -- ============ 3b. 补充特征(锐智语义抽取, 服务于规律分析/压降) ============
    has_injury VARCHAR(10),                                 -- 是否造成人员受伤: 是/否/未载明
    injury_severity VARCHAR(20),                            -- 伤情: 无/轻微伤/轻伤/重伤/死亡/未载明
    party_relationship VARCHAR(30),                         -- 当事人关系: 陌生人/熟人朋友/邻里/亲属家庭/夫妻情侣/同事/同学/医患/商家顾客/其他/未载明
    conflict_nature VARCHAR(20),                            -- 矛盾性质: 临时起意/偶发口角/长期积怨/未载明
    people_count_est VARCHAR(20),                           -- 涉及打架人数(估计/原文)
    involves_minor VARCHAR(10),                             -- 是否涉及未成年人: 是/否/未载明
    disposition_category VARCHAR(30),                       -- 处置结果分类: 当场调解/治安调解/行政处罚/刑事立案处理/劝离/移交其他部门/无需处置/未载明

    -- ============ 3c. 时段维度(代码按 calltime 推导, 不耗模型) ============
    incident_hour SMALLINT,                                 -- 报警小时 0-23
    time_period VARCHAR(10),                                -- 时段: 凌晨/上午/下午/傍晚/夜间
    weekday VARCHAR(10),                                    -- 星期一..星期日
    is_weekend BOOLEAN,                                     -- 是否周末

    -- ============ 4. 审计字段 ============
    reason_evidence VARCHAR(500),                           -- 打架原因原文(审计)
    location_address_evidence VARCHAR(500),                 -- 地点(警情地址)原文(审计)
    location_replies_evidence VARCHAR(500),                 -- 地点(处警情况)原文(审计)
    model_name VARCHAR(50),                                 -- 使用的模型
    extract_status VARCHAR(20),                             -- ok / failed / skipped(非有效案情未入模)
    extract_error TEXT,                                     -- 失败原因(便于失败重跑)
    raw_answer TEXT,                                        -- 模型原始返回(审计)
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,       -- 提取执行时间
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,         -- 记录更新时间

    -- 业务唯一约束: 一条警情一行, 支持 ON CONFLICT UPSERT
    CONSTRAINT uq_dajia_feature_caseno UNIQUE (caseno)
);

-- 增量水位线加速
CREATE INDEX IF NOT EXISTS idx_zq_dajia_feat_source_updatetime
ON jcgkzx_monitor.zq_dajia_feature_extract (source_updatetime);

-- 常用分析维度加速
CREATE INDEX IF NOT EXISTS idx_zq_dajia_feat_calltime
ON jcgkzx_monitor.zq_dajia_feature_extract (calltime);

CREATE INDEX IF NOT EXISTS idx_zq_dajia_feat_reason_cat
ON jcgkzx_monitor.zq_dajia_feature_extract (brawl_reason_category);

CREATE INDEX IF NOT EXISTS idx_zq_dajia_feat_extract_status
ON jcgkzx_monitor.zq_dajia_feature_extract (extract_status);

-- --------------------------------------------------
-- 枚举参考(应用层校验, 不做 DB 约束以便后续调整):
--   打架原因分类: 情感纠纷 / 经济纠纷 / 酒后滋事 / 邻里纠纷 / 土地纠纷 /
--                交通纠纷 / 消费纠纷 / 学生间（同事间）琐事纠纷 / 医疗纠纷 / 其他纠纷
--   地点分类:     农村 / 街面 / 一般商店 / 学校（包含学校附近） / 住宅区 /
--                娱乐场所（包含酒店） / 医院 / 机关政府 / 工厂公司 / 山林野外 / 其他
-- --------------------------------------------------
