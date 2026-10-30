package edu.tju.lab2;

import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SeckillService {
    private final SeckillMapper mapper;
    public SeckillService(SeckillMapper mapper) { this.mapper=mapper; }
    public List<Activity> activities() { return mapper.activities(); }
    public Activity activity(long id) {
        Activity a=mapper.activity(id);
        if (a==null) throw new BusinessException("NOT_FOUND","活动不存在",404);
        return a;
    }
    public List<Order> orders(String userId) { return mapper.userOrders(userId); }
    public Order result(String requestId,String userId) {
        Order o=mapper.byRequest(requestId);
        if (o==null || !o.userId().equals(userId)) throw new BusinessException("NOT_FOUND","未找到该用户的订单",404);
        return o;
    }
    @Transactional
    public Order place(long activityId,String userId,String requestId) {
        // 基础版按活动行加锁，优先保证正确性；这也形成后续优化的比较基线。
        Activity a=mapper.lockActivity(activityId);
        if (a==null) throw new BusinessException("NOT_FOUND","活动不存在",404);
        Order existing=mapper.byRequest(requestId);
        if (existing!=null) {
            if (existing.activityId()==activityId && existing.userId().equals(userId)) return existing;
            throw new BusinessException("REQUEST_CONFLICT","请求编号已经用于其他购买请求",409);
        }
        if (mapper.byBuyer(activityId,userId)!=null)
            throw new BusinessException("ALREADY_PURCHASED","每位用户每场活动限购一件",409);
        switch (a.getState()) {
            case "DISABLED" -> throw new BusinessException("DISABLED","活动暂未开放",409);
            case "UPCOMING" -> throw new BusinessException("NOT_STARTED","活动尚未开始",409);
            case "ENDED" -> throw new BusinessException("ENDED","活动已经结束",409);
            case "SOLD_OUT" -> throw new BusinessException("SOLD_OUT","商品已售罄",409);
            default -> { }
        }
        // SQL 再次检查数据库时间与库存，防止锁等待或执行期间活动过期。
        if (mapper.decrement(activityId)!=1)
            throw new BusinessException("UNAVAILABLE","库存或活动状态已变化，请刷新后重试",409);
        Order order=new Order(UUID.randomUUID().toString(),requestId,activityId,userId,
            a.productName(),a.seckillPrice(),1,"SUCCESS",null);
        mapper.insertOrder(order);
        return mapper.byRequest(requestId);
    }
}
