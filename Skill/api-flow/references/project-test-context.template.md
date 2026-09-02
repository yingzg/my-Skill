# Project Test Context

> 本文件为 api-flow 工具的鉴权和数据库配置模板。
> 请复制为 `docs/api-test/project-test-context.md` 并填入实际值。

## 环境信息

```yaml
environment: local          # local | dev | staging
base_url: http://localhost:8080
```

## 鉴权配置

```yaml
auth_type: oauth2           # oauth2 | bearer | apikey | none

# OAuth2 配置
token_url: http://localhost:8080/oauth/token
client_id: test-client
client_secret: ${OAUTH_SECRET}   # 从环境变量读取
username: test_admin
password: test123

# Bearer token 配置（固定 token）
# auth_type: bearer
# token: your-fixed-token-here
```

## 数据库配置

```yaml
database:
  host: localhost
  port: 3306
  user: root
  password: ${DB_PASSWORD}
  database: test_db
```

## 业务约定

```yaml
# 租户/渠道隔离
headers:
  X-Tenant-Id: "test-tenant"
  X-Channel: "test-channel"

# 测试数据命名约定
test_data_prefix: "TEST_"
```
