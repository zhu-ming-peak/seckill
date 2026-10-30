-- token 防止旧回调撤销新请求；状态判断防止重复补偿。
if redis.call('HGET',KEYS[1],'user:'..ARGV[1])~=ARGV[2] then return 0 end
if redis.call('HGET',KEYS[1],'token:'..ARGV[2])~='PENDING' then return 0 end
if ARGV[3]=='COMMIT' then
  redis.call('HSET',KEYS[1],'token:'..ARGV[2],'COMMITTED')
else
  redis.call('HINCRBY',KEYS[1],'stock',1)
  redis.call('HDEL',KEYS[1],'user:'..ARGV[1],'token:'..ARGV[2])
end
return 1
