if redis.call('EXISTS',KEYS[1]) == 0 then
  redis.call('HSET',KEYS[1],'stock',ARGV[1])
  redis.call('EXPIRE',KEYS[1],ARGV[2])
end
return tonumber(redis.call('HGET',KEYS[1],'stock'))
