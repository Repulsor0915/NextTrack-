  1. 目的与边界：两个 raw CSV → 统一记录 → catalogue.json／报告
     ／manifest → SQLite 导入；预处理不做推荐排序。

  2. 两个输入来源：各自路径、来源与校验和、不同栏位名；明确
     dataset.csv 和 tracks.csv 都有 album_name。

  3. 统一输出格式：id、title、原样保存的 artist_display、
     album_display、genre、explicit、year、八维特征；缺歌手/专辑
     如何用 null 表示。

  4. 审核与合并规则：哪些字段必填、八维范围、按 track ID 去重、
     两来源同 ID 时谁优先，以及拒绝原因如何统计。

  5. 重现命令：从项目根目录或 backend 目录运行的命令各给一套，包
     含 audit-only、生成、dry-run 导入。

  6. 产物与版本：三个输出文件、checksum、不可覆盖非空目录，以及
     旧版实验结果属于哪个 catalogue 版本。

  7. 验证方式：小样本测试、manage.py check、导入前后
     catalogue_status，确认当前使用 db.schema-final.sqlite3。

