-- 仅由持有 MySQL 活动行锁的受理/恢复流程调用。
-- 数据库剩余库存减去持久化 ACCEPTED 请求才是可分配资格。
redis.call('DEL',KEYS[1])
redis.call('HSET',KEYS[1],'stock',ARGV[1])
for i=3,#ARGV,2 do
  redis.call('HSET',KEYS[1],'user:'..ARGV[i],ARGV[i+1],'token:'..ARGV[i+1],'PENDING')
end
redis.call('EXPIRE',KEYS[1],ARGV[2])
return tonumber(ARGV[1])
