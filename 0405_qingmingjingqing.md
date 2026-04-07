# 涓婚婧愪笌涓婚鏈€缁堥厤缃竻鍗?

杩欎笁濂楁柟妗堝叡鐢ㄥ悓涓€涓暟鎹簮 `璀︽儏鐩戞祴`锛屽彧鏄富棰樿繃婊ゆ潯浠朵笉鍚屻€?

## 鍏叡鏁版嵁婧愰厤缃?

鍏堝湪鈥滄暟鎹簮鈥濋噷褰曞叆 1 鏉″叕鍏辨暟鎹簮锛屽悗闈笁涓富棰橀兘澶嶇敤瀹冦€?

- `source_name`锛歚璀︽儏鐩戞祴`
- `source_code`锛歚jingqing_monitor`
- `source_type`锛歚dsjfx_case_list`
- `enabled`锛歚true`
- `schedule.interval_value`锛歚10`
- `schedule.interval_unit`锛歚minute`
- `schedule.timezone`锛歚Asia/Shanghai`
- `source_config`锛氳涓嬫柟 JSON

```json
{
  "credential_ref": {
    "username_env": "LOGIN_USERNAME",
    "password_env": "LOGIN_PASSWORD"
  },
  "login_url": "http://your-dsjfx-host/dsjfx/login",
  "api_url": "http://your-dsjfx-host/dsjfx/case/list",
  "time_range": {
    "mode": "rolling_days",
    "days_back": 3
  },
  "fetch_profile": {
    "page_size": 5000,
    "max_pages": 50
  },
  "base_params": {}
}
```

璇存槑锛?
- 姣忔鏁版嵁婧愭墽琛屾椂锛岄兘浼氭姄鏈€杩?3 澶╃殑 `/dsjfx/case/list` 鏁版嵁銆?
- `page_size=5000` 鐨勬剰鎬濇槸灏介噺澶ч〉鎷夊彇锛屽噺灏戝垎椤佃姹傛鏁般€?
- `base_params` 闄ゆ椂闂寸浉鍏冲弬鏁板鍏堜繚鎸佺┖锛岀敱涓婚灞傚仛浜屾杩囨护銆?
- 涓婚鏈韩娌℃湁鍗曠嫭瀹氭椂鍣紝瀹冭窡鐫€鏁版嵁婧愪竴璧疯繍琛屻€?

## 鏂规涓€锛氭竻鏄庢秹鏋楀湴/鍧熷湴璀︽儏

### 涓婚閰嶇疆

- `theme_name`锛歚娓呮槑娑夋灄鍦?鍧熷湴璀︽儏`
- `theme_code`锛歚qingming_selin_fendi_jq`
- `priority`锛歚100`
- `dedup_mode`锛歚permanent`
- `dedup_key_template`锛歚{event_key}`
- `message_template`锛氳涓嬫柟鐭俊妯℃澘

`filter_expr` 鐩存帴褰曞叆涓嬮潰杩欐锛?

```json
{
  "any": [
    {
      "field": "caseContents",
      "op": "contains_any",
      "value": [
        "娓呮槑", "鎵", "绁壂", "涓婂潫", "鍧熷湴", "鍧熷", "澧撳湴", "澧撳洯",
        "鍧熷ご", "鏋楀湴", "灞辨灄", "灞卞満", "鏋楀尯", "鏋楁潈", "鍦扮晫", "鐑х焊", "鐒氶"
      ]
    },
    {
      "field": "occurAddress",
      "op": "contains_any",
      "value": ["鏋楀湴", "鍧熷湴", "澧撳湴", "澧撳洯", "鍧熷ご", "灞辨灄", "灞卞満", "鏋楀尯"]
    },
    {
      "field": "replies",
      "op": "contains_any",
      "value": [
        "宸插嚭璀?, "宸插埌鍦?, "宸插缃?, "宸插姖绂?, "宸茶皟瑙?, "宸插钩鎭?, "宸茬Щ浜?
      ]
    }
  ]
}
```

### 涓婚鎺ユ敹瑙勫垯

鏂板缓 1 鏉♀€滀富棰樻帴鏀惰鍒欌€濓紝褰曞叆鏃惰繖鏍峰～锛?

- `rule_name`锛歚娓呮槑娑夋灄鍦?鍧熷湴鍥哄畾鎺ユ敹浜篳
- `rule_type`锛歚fixed_receivers`
- `source_field`锛氱暀绌?
- `target_match_field`锛氫繚鎸侀粯璁?`sspcsdm`
- `priority`锛歚100`
- `enabled`锛氬嬀閫?
- `fixed_receivers`锛氫竴琛屼竴涓墜鏈哄彿锛屾垨鐢ㄩ€楀彿鍒嗛殧
- `filter_json`锛歚{}`

璇存槑锛?
- `fixed_receivers` 妯″紡涓嬶紝`source_field` 涓嶅弬涓庤绠椼€?
- `filter_json` 涔熶笉鍋氶檺鍒讹紝鐣欑┖鍗冲彲銆?

### 鐭俊妯℃澘

鐭俊妯℃澘鐩存帴褰曞叆涓嬮潰杩欐锛?

```text
銆愭竻鏄庢秹鏋楀湴/鍧熷湴璀︽儏銆?
鎶ヨ鏃堕棿锛歿alarmTime}
娲惧嚭鎵€锛歿duty_dept_name}
璀︽儏缂栧彿锛歿case_no}
鍦扮偣锛歿occur_address}
鎶ヨ鍐呭锛歿case_contents}
澶勮鎯呭喌锛歿replies}
鍛戒腑鍏抽敭瀛楋細{鍛戒腑鍏抽敭瀛梷
```

璇存槑锛?
- `鍛戒腑鍏抽敭瀛梎 鐜板湪浼氳嚜鍔ㄨ緭鍑烘垚 `瀛楁鏍囩鈫掑懡涓€糮銆?
- 渚嬪 `caseContents` 鍛戒腑 `鍧熷湴`锛岀煭淇￠噷灏辨槸 `鍛戒腑鍏抽敭瀛楋細鎶ヨ鍐呭鈫掑潫鍦癭銆?

## 鏂规浜岋細绮剧绫昏鎯?

### 涓婚閰嶇疆

- `theme_name`锛歚绮剧绫昏鎯卄
- `theme_code`锛歚mental_case_jq`
- `priority`锛歚100`
- `dedup_mode`锛歚permanent`
- `dedup_key_template`锛歚{event_key}`
- `message_template`锛氳涓嬫柟鐭俊妯℃澘

`filter_expr` 鐩存帴褰曞叆涓嬮潰杩欐锛?

```json
{
  "any": [
    {
      "field": "caseContents",
      "op": "regex",
      "value": "绮剧鐥厊绮剧闅滅|绮剧寮傚父|绮剧鍙戠梾|鐘梾|鑲囦簨鑲囩ジ"
    },
    {
      "field": "replies",
      "op": "regex",
      "value": "绮剧鐥厊绮剧闅滅|绮剧寮傚父|绮剧鍙戠梾|鐘梾|鑲囦簨鑲囩ジ"
    }
  ]
}
```

### 涓婚鎺ユ敹瑙勫垯

鏂板缓 1 鏉♀€滀富棰樻帴鏀惰鍒欌€濓紝褰曞叆鏃惰繖鏍峰～锛?

- `rule_name`锛歚绮剧绫昏鎯呭浐瀹氭帴鏀朵汉`
- `rule_type`锛歚fixed_receivers`
- `source_field`锛氱暀绌?
- `target_match_field`锛氫繚鎸侀粯璁?`sspcsdm`
- `priority`锛歚100`
- `enabled`锛氬嬀閫?
- `fixed_receivers`锛氫竴琛屼竴涓墜鏈哄彿锛屾垨鐢ㄩ€楀彿鍒嗛殧
- `filter_json`锛歚{}`

### 鐭俊妯℃澘

鐭俊妯℃澘鐩存帴褰曞叆涓嬮潰杩欐锛?

```text
銆愮簿绁炵被璀︽儏銆?
鎶ヨ鏃堕棿锛歿alarmTime}
娲惧嚭鎵€锛歿duty_dept_name}
璀︽儏缂栧彿锛歿case_no}
鍦扮偣锛歿occur_address}
鎶ヨ鍐呭锛歿case_contents}
澶勮鎯呭喌锛歿replies}
鍛戒腑鍏抽敭瀛楋細{鍛戒腑鍏抽敭瀛梷
```

璇存槑锛?
- 濡傛灉 `caseContents` 鍛戒腑 `绮剧闅滅`锛岀煭淇￠噷灏辨槸 `鍛戒腑鍏抽敭瀛楋細鎶ヨ鍐呭鈫掔簿绁為殰纰峘銆?

## 鏂规涓夛細鎵█鏋佺璀︽儏

### 涓婚閰嶇疆

- `theme_name`锛歚鎵█鏋佺璀︽儏`
- `theme_code`锛歚yyjd_jq`
- `priority`锛歚100`
- `dedup_mode`锛歚permanent`
- `dedup_key_template`锛歚{event_key}`
- `message_template`锛氳涓嬫柟鐭俊妯℃澘

璇存槑锛?
- 杩欎竴鐗堟部鐢?`jingqing_fenxi` 鐨勫叧閿瘝浜屾杩囨护鎬濊矾锛屽彧鍋氭姤璀﹀唴瀹瑰拰澶勮鎯呭喌鐨勫叧閿瘝鍛戒腑銆?
- `dedup_key_template` 淇濇寔 `{event_key}`锛屽敖閲忔妸鐭俊骞冲彴 `EID` 闀垮害鍘嬩綆锛涘鏋滃悗闈㈣繕鎻愮ず瓒呴暱锛屽氨缁х画缂╃煭 `theme_code`銆?
- 绗竴鐗堝厛涓嶅姞鍒嗗眬銆佹淳鍑烘墍绛夐澶栫淮搴︼紝閬垮厤鎶婂懡涓寖鍥存敹寰楄繃绱с€?

`filter_expr` 鐩存帴褰曞叆涓嬮潰杩欐锛?

```json
{
  "any": [
    {
      "field": "caseContents",
      "op": "contains_any",
      "value": [
        "鎶ュ绀句細", "鏉€浜?, "鏀剧伀", "鐖嗙偢", "鎶曟瘨", "鎸佸垁", "鐮嶄汉", "鎹呬汉",
        "濞佽儊", "鎭愬悡", "鎵█", "鍚屽綊浜庡敖", "鑷潃", "杞荤敓",
        "鏋佺瑷€璁?, "鏋佺琛屼负", "鏆村姏鍊惧悜"
      ]
    },
    {
      "field": "replies",
      "op": "contains_any",
      "value": [
        "鎶ュ绀句細", "鏉€浜?, "鏀剧伀", "鐖嗙偢", "鎶曟瘨", "鎸佸垁", "鐮嶄汉", "鎹呬汉",
        "濞佽儊", "鎭愬悡", "鎵█", "鍚屽綊浜庡敖", "鑷潃", "杞荤敓",
        "鏋佺瑷€璁?, "鏋佺琛屼负", "鏆村姏鍊惧悜"
      ]
    }
  ]
}
```

### 涓婚鎺ユ敹瑙勫垯

鏂板缓 1 鏉♀€滀富棰樻帴鏀惰鍒欌€濓紝褰曞叆鏃惰繖鏍峰～锛?

- `rule_name`锛歚鎵█鏋佺璀︽儏鍥哄畾鎺ユ敹浜篳
- `rule_type`锛歚fixed_receivers`
- `source_field`锛氱暀绌?
- `target_match_field`锛氫繚鎸侀粯璁?`sspcsdm`
- `priority`锛歚100`
- `enabled`锛氬嬀閫?
- `fixed_receivers`锛氫竴琛屼竴涓墜鏈哄彿锛屾垨鐢ㄩ€楀彿鍒嗛殧
- `filter_json`锛歚{}`

璇存槑锛?
- `fixed_receivers` 妯″紡涓嬶紝`source_field` 涓嶅弬涓庤绠椼€?
- `filter_json` 涔熶笉鍋氶檺鍒讹紝鐣欑┖鍗冲彲銆?

### 鐭俊妯℃澘

鐭俊妯℃澘鐩存帴褰曞叆涓嬮潰杩欐锛?

```text
銆愭壃瑷€鏋佺璀︽儏銆?
鎶ヨ鏃堕棿锛歿alarmTime}
娲惧嚭鎵€锛歿duty_dept_name}
璀︽儏缂栧彿锛歿case_no}
鍦扮偣锛歿occur_address}
鎶ヨ鍐呭锛歿case_contents}
澶勮鎯呭喌锛歿replies}
鍛戒腑鍏抽敭瀛楋細{鍛戒腑鍏抽敭瀛梷
```

璇存槑锛?
- 濡傛灉 `caseContents` 鍛戒腑 `鎵█鏀剧伀`锛岀煭淇￠噷灏辨槸 `鍛戒腑鍏抽敭瀛楋細鎶ヨ鍐呭鈫掓壃瑷€鏀剧伀`銆?
- 濡傛灉 `replies` 鍛戒腑 `濞佽儊`锛岀煭淇￠噷灏辨槸 `鍛戒腑鍏抽敭瀛楋細澶勮鎯呭喌鈫掑▉鑳乣銆?
- `alarmTime` 鏄簮鏁版嵁閲岀殑鎶ヨ鏃堕棿锛涘鏋滀綘鎯虫墦鍗板彟涓€鍒?`callTime`锛屽彲浠ョ洿鎺ュ湪妯℃澘閲岀敤 `{callTime}`銆?

## 褰曞叆椤哄簭

1. 鍏堝綍鍏ュ叕鍏辨暟鎹簮 `璀︽儏鐩戞祴`銆?
2. 鍐嶅綍鍏?`娓呮槑娑夋灄鍦?鍧熷湴璀︽儏` 涓婚鍜屽畠鐨勫浐瀹氭帴鏀惰鍒欍€?
3. 鍐嶅綍鍏?`绮剧绫昏鎯卄 涓婚鍜屽畠鐨勫浐瀹氭帴鏀惰鍒欍€?
4. 鍐嶅綍鍏?`鎵█鏋佺璀︽儏` 涓婚鍜屽畠鐨勫浐瀹氭帴鏀惰鍒欍€?
5. 鏈€鍚庡垎鍒偣鈥滄紨缁冣€濓紝纭鐭俊妯℃澘鍜屾帴鏀舵墜鏈哄彿閮芥纭€?

## 琛ュ厖璇存槑

- 鏁版嵁婧愭瘡 10 鍒嗛挓璺戜竴娆★紝杩?3 澶╃殑鏁版嵁浼氬湪姣忔杩愯鏃堕噸鏂版媺鍙栥€?
- 涓婚娌℃湁鍗曠嫭鐨勫畾鏃惰疆璇紝瀹冭窡鐫€鏁版嵁婧愪竴璧锋墽琛屻€?
- 濡傛灉澶氫釜鍏抽敭璇嶉兘鍛戒腑锛岀郴缁熶細鎸?`filter_expr` 閲屼粠鍓嶅埌鍚庣殑椤哄簭锛屽彇绗竴涓懡涓殑鍏抽敭璇嶆潵灞曠ず銆?
- 鐜板湪 `鍛戒腑鍏抽敭瀛梎 鐨勬牸寮忓凡缁忕粺涓€鎴?`瀛楁鏍囩鈫掑懡涓€糮锛岄€傚悎鐩存帴缁欒繍缁村拰鍊肩彮浜哄憳鐪嬨€?
- 涓変釜涓婚閮藉彲浠ユ寕鍚屼竴涓?`璀︽儏鐩戞祴` 鏁版嵁婧愶紝鎵ц鏃跺垎鍒寜鑷繁鐨勫叧閿瘝杩囨护銆?
---
鍙互锛屾垜缁欎綘鐩存帴鎷嗘垚鈥滃彲涓婁紶 ZIP 鍖呮ā鏉?+ 浠诲姟閰嶇疆妯℃澘鈥濓紝骞舵妸 `0123_dxpt_ceshi.py` 璇ユ€庝箞鍙戠煭淇¤娓呮銆?

**鍏堟妸鍏抽敭鐐硅閫?*

`runtime_config` 涓嶆槸 `.env`锛屼篃涓嶆槸鎶婅处鍙峰瘑鐮佸啓杩涜剼鏈?ZIP 浠ｇ爜閲屻€傚畠鏄€滀换鍔＄骇閰嶇疆 JSON鈥濓紝骞冲彴鎵ц `run(context)` 鏃朵細鎶婂畠浼犵粰鑴氭湰銆傝剼鏈噷鍙細娑堣垂鑷繁鏄犲皠鍒扮殑閭ｄ簺閿€?

瀵硅繖涓や釜鑴氭湰鏉ヨ锛?

- `0123_dxpt_ceshi.py` 鐨勮嚜瀹氫箟浠诲姟鍏ュ彛鏄?`run(context)`锛屽畠褰撳墠鍚冪殑鏄?`kingbase_*`銆乣dxpt_start_date`銆乣limit`銆?
- `zq_kshddpt_dsjfx_jq.py` 鐨勮嚜瀹氫箟浠诲姟鍏ュ彛涔熸槸 `run(context)`锛屽畠鍚冪殑鏄?`zq_*` 涓€鏁村鍙傛暟銆?
- 璐﹀彿瀵嗙爜涓嶈纭紪鐮佽繘 ZIP 浠ｇ爜閲岋紝浼樺厛鏀惧湪浠诲姟鐨?`runtime_config` 鎴栧鍣?`.env`銆?
- 濡傛灉浣犺璧扳€滆嚜瀹氫箟浠诲姟鈥濊繖鏉¤矾锛宍0123_dxpt_ceshi.py` 鐨勭煭淇″彂閫佷笉鏄剼鏈嚜宸卞彂锛岃€屾槸骞冲彴鍦ㄤ换鍔¤鍒欏懡涓悗鍙戙€?

**1. `0123_dxpt_ceshi.py`锛氬彲涓婁紶 ZIP 鍖呮ā鏉?*

鐩綍缁撴瀯锛?

```text
0123_dxpt_ceshi.zip
鈹溾攢 0123_dxpt_ceshi.py
鈹斺攢 manifest.json
```

`manifest.json`锛?

```json
{
  "entry_file": "0123_dxpt_ceshi.py",
  "entry_func": "run",
  "script_type": "python_zip"
}
```

**2. `0123_dxpt_ceshi.py`锛氫换鍔￠厤缃?JSON 妯℃澘**

寤鸿浣犲厛杩欐牱閰嶏紝鍏堣瀹冭蛋骞冲彴鐭俊瑙勫垯鍙戯細

```json
{
  "task_name": "0123_dxpt_ceshi",
  "script_id": "<上传后脚本ID>",
  "script_version_id": "<上传后版本ID>",
  "message_template_id": null,
  "enabled": true,
  "dedup_key_expr": "",
  "dedup_window_minutes": 12,
  "runtime_config": {
    "kingbase_host": "your-kingbase-host",
    "kingbase_port": 5432,
    "kingbase_dbname": "your-db",
    "kingbase_user": "your-user",
    "kingbase_password": "your-password",
    "dxpt_start_date": "2026-04-01",
    "limit": 0
  },
  "schedule": {
    "interval_value": 2,
    "interval_unit": "hour",
    "timezone": "Asia/Shanghai",
    "start_at": null,
    "end_at": null,
    "enabled": true
  }
}
```

**3. `0123_dxpt_ceshi.py`锛氬繀椤诲啀閰嶄竴鏉℃帴鏀惰鍒?*

濡傛灉浣犳兂鈥滅洿鎺ヨ兘鍙戠煭淇♀€濓紝杩樿缁欒繖涓换鍔″姞涓€鏉¤鍒欍€備笉鐒跺畠鍛戒腑鍚庡彧浼氭湁缁撴灉锛屼笉浼氭湁鎺ユ敹浜恒€?

鎴戝缓璁厛鐢?`field_match`锛屾寜娲惧嚭鎵€浠ｇ爜鍙戯細

```json
{
  "rule_name": "0123鎸夋淳鍑烘墍鍙戦€?,
  "rule_type": "field_match",
  "priority": 100,
  "enabled": true,
  "source_field": "sspcsdm",
  "target_table": "jcgkzx_autotask.org_contact",
  "target_match_field": "sspcsdm",
  "target_mobile_field": "mobile",
  "include_self": true,
  "include_county": false,
  "include_city": false,
  "filter_json": {},
  "fixed_receivers": []
}
```

杩欐潯瑙勫垯鐨勬剰鎬濇槸锛氳剼鏈繑鍥炵殑 `sspcsdm` 鍘昏仈绯讳汉琛ㄩ噷鎵惧搴旀淳鍑烘墍鑱旂郴浜猴紝鍐嶅彇鎵嬫満鍙峰彂鐭俊銆?

濡傛灉浣犲彧鎯冲厛娴嬭瘯锛屼篃鍙互鎶婅鍒欐敼鎴?`fixed_receivers`锛岀洿鎺ュ～鎵嬫満鍙凤紝浣嗛偅灏变笉鏄寜娲惧嚭鎵€鑷姩鍒嗗彂浜嗐€?

**4. `zq_kshddpt_dsjfx_jq.py`锛氬彲涓婁紶 ZIP 鍖呮ā鏉?*

鐩綍缁撴瀯锛?

```text
zq_kshddpt_dsjfx_jq.zip
鈹溾攢 zq_kshddpt_dsjfx_jq.py
鈹斺攢 manifest.json
```

`manifest.json`锛?

```json
{
  "entry_file": "zq_kshddpt_dsjfx_jq.py",
  "entry_func": "run",
  "script_type": "python_zip"
}
```

**5. `zq_kshddpt_dsjfx_jq.py`锛氫换鍔￠厤缃?JSON 妯℃澘**

杩欎釜鑴氭湰浣犺浜嗗彧鍚屾锛屼笉鍙戠煭淇★紝鎵€浠ワ細

- `message_template_id` 鐣欑┖
- 涓嶈閰嶄换浣曟帴鏀惰鍒?
- 瀹冨氨鍙礋璐ｈ窇鍚屾缁撴灉锛屼笉浼氳繘鐭俊鍙戦€侀摼璺?

```json
{
  "task_name": "zq_kshddpt_dsjfx_jq",
  "script_id": "<涓婁紶鍚庤剼鏈琁D>",
  "script_version_id": "<涓婁紶鍚庣増鏈琁D>",
  "message_template_id": null,
  "enabled": true,
  "dedup_key_expr": "",
  "dedup_window_minutes": 12,
  "runtime_config": {
    "zq_login_url": "http://68.253.2.111/dsjfx/login",
    "zq_login_username": "your-login-user",
    "zq_login_password": "your-login-password",
    "zq_api_url": "http://68.253.2.111/dsjfx/case/list",
    "zq_db_host": "your-kingbase-host",
    "zq_db_port": 5432,
    "zq_db_name": "your-db",
    "zq_db_user": "your-user",
    "zq_db_password": "your-password",
    "zq_db_schema": "ywdata",
    "zq_begin_days_ago": 3,
    "zq_page_size": 99999,
    "zq_page_num": 1
  },
  "schedule": {
    "interval_value": 2,
    "interval_unit": "hour",
    "timezone": "Asia/Shanghai",
    "start_at": null,
    "end_at": null,
    "enabled": true
  }
}
```

**6. 浣犲垰鎵嶉棶鐨?`runtime_config` 鍒板簳鏄粈涔堟剰鎬?*

鏈€鐩存帴鐨勭悊瑙ｆ槸锛?

- 瀹冩槸鈥滀换鍔¤繍琛屾椂鍙傛暟鈥?
- 骞冲彴浼氭妸瀹冧紶缁欒剼鏈殑 `run(context)`
- 鑴氭湰鑷繁鍐冲畾璇诲彇鍝簺閿?
- 瀹冧笉鏄鍣?`.env`
- 瀹冧篃涓嶅簲璇ュ彉鎴愯剼鏈?ZIP 閲岀殑纭紪鐮佽处鍙峰瘑鐮?

瀵?`0123_dxpt_ceshi.py` 鏉ヨ锛屽湪鑷畾涔変换鍔℃ā寮忎笅锛宍runtime_config` 涓昏鏀?Kingbase 杩炴帴鍜?`dxpt_start_date`銆? 
瀵?`zq_kshddpt_dsjfx_jq.py` 鏉ヨ锛宍runtime_config` 鍙互鏀剧櫥褰曘€佹帴鍙ｃ€並ingbase 鍜屽垎椤靛弬鏁般€?

濡傛灉浣犳効鎰忥紝鎴戜笅涓€姝ュ彲浠ョ户缁府浣犳妸杩欎袱濂楁ā鏉垮啀鏁寸悊鎴愶細
- 涓€浠藉彲鐩存帴澶嶅埗鍒板墠绔〃鍗曠殑鈥滈€愬瓧娈靛～鍐欐竻鍗曗€?
- 涓€浠借兘鐩存帴鎵撳寘鐨?ZIP 鐩綍绀轰緥缁撴瀯

杩欐牱浣犲氨鍙互鐩存帴鐓х潃涓婁紶锛屼笉鐢ㄨ嚜宸卞啀鎷笺€
