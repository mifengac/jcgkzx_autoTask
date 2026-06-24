-- --------------------------------------------------
-- 警情文本号码提取目标表结构定义 (jcgkzx_monitor.zq_jingqing_number_extract)
-- 包含原始提取字段及 zq_kshddpt_dsjfx_jq 源表关联字段
-- --------------------------------------------------

CREATE SCHEMA IF NOT EXISTS jcgkzx_monitor;

-- 如果需要重置，请手动运行 DROP TABLE jcgkzx_monitor.zq_jingqing_number_extract;
CREATE TABLE IF NOT EXISTS jcgkzx_monitor.zq_jingqing_number_extract (
    id BIGSERIAL PRIMARY KEY,
    
    -- 1. 原始提取的核心标识和结果字段
    caseno VARCHAR(100) NOT NULL,                           -- 警情编号
    extract_field VARCHAR(50) NOT NULL,                     -- 提取源字段 (如 casecontents 或 replies)
    number_type VARCHAR(50) NOT NULL,                       -- 号码类型 (如 ID_CARD, PHONE_MOBILE, BANK_CARD 等)
    number_value VARCHAR(100) NOT NULL,                     -- 提取出的号码明文
    number_masked VARCHAR(100),                             -- 脱敏后的号码
    is_valid BOOLEAN,                                       -- 是否通过校验
    confidence INT,                                         -- 置信度 (0-100)
    match_pattern VARCHAR(100),                             -- 命中的匹配规则ID
    context_snippet VARCHAR(500),                           -- 上下文切片
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,       -- 提取执行时间
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,         -- 记录更新时间
    
    -- 2. 新增的来自源表 zq_kshddpt_dsjfx_jq 的基础信息字段
    source_updatetime TIMESTAMP,                            -- 源表数据更新时间 (增量同步水位线依据)
    calltime TIMESTAMP,                                     -- 报警时间
    cmdid VARCHAR(50),                                      -- 地区编码
    cmdname VARCHAR(100),                                   -- 地区名称
    callerphone VARCHAR(50),                                -- 报警电话
    callername VARCHAR(100),                                -- 报警人
    occuraddress VARCHAR(500),                              -- 报警地址
    casecontents TEXT,                                      -- 报警内容
    replies TEXT,                                           -- 处警情况
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
    neworicharasubclass VARCHAR(50),                        -- 原始警情四类代码
    neworicharasubclassname VARCHAR(100),                   -- 原始警情四类名称
    newcharacategory VARCHAR(50),                           -- 确认警情大类代码
    newcharacategoryname VARCHAR(100),                      -- 确认警情大类名称
    newcharatype VARCHAR(50),                               -- 确认警情二类代码
    newcharatypename VARCHAR(100),                          -- 确认警情二类名称
    newcharasubcategory VARCHAR(50),                        -- 确认警情三类代码
    newcharasubcategoryname VARCHAR(100),                   -- 确认警情三类名称
    newcharasubclass VARCHAR(50),                           -- 确认警情四类代码
    newcharasubclassname VARCHAR(100),                      -- 确认警情四类名称
    lngofcriterion VARCHAR(50),                             -- 警情经度
    latofcriterion VARCHAR(50),                             -- 警情纬度
    casemark VARCHAR(200),                                  -- 警情标签
    casemarkno VARCHAR(200),                                -- 警情标签代码
    casemarkok VARCHAR(200),                                -- 确认警情标签
    casemarkokno VARCHAR(200),                              -- 确认警情标签代码
    standardcaseno VARCHAR(100),                            -- 部警情编号
    
    -- 3. 业务唯一约束：防止同一警情、同一字段提取出的相同类型号码被重复录入 (支持 ON CONFLICT UPSERT)
    CONSTRAINT uq_jingqing_extract UNIQUE (caseno, extract_field, number_type, number_value)
);

-- 4. 索引加速设计
-- 用于增量抽取的水位线加速
CREATE INDEX IF NOT EXISTS idx_zq_jq_num_ext_source_updatetime 
ON jcgkzx_monitor.zq_jingqing_number_extract (source_updatetime);

-- 用于通过警情编号快速查询已提取记录
CREATE INDEX IF NOT EXISTS idx_zq_jq_num_ext_caseno 
ON jcgkzx_monitor.zq_jingqing_number_extract (caseno);
