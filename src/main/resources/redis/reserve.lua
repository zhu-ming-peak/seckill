-- 所有库存和资格字段位于同一活动 Hash，避免部分键独立过期。
-- 初始化库存由调用方在 MySQL 活动行锁内读取，仅首次创建时写入。
if redis.call('EXISTS',KEYS[1]) == 0 then
  redis.call('HSET',KEYS[1],'stock',ARGV[1])
  redis.call('EXPIRE',KEYS[1],ARGV[4])
end
local userField='user:'..ARGV[2]
if redis.call('HEXISTS',KEYS[1],userField)==1 then return 2 end
local stock=tonumber(redis.call('HGET',KEYS[1],'stock'))
if not stock or stock<=0 then return 1 end
redis.call('HINCRBY',KEYS[1],'stock',-1)
redis.call('HSET',KEYS[1],userField,ARGV[3],'token:'..ARGV[3],'PENDING')
return 0
