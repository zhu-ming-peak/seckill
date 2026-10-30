package edu.tju.lab2;
import java.math.BigDecimal;
import java.time.LocalDateTime;
public record ActivityData(long id,long productId,String title,BigDecimal seckillPrice,
                           int initialStock,int stock,LocalDateTime startTime,
                           LocalDateTime endTime,String status,LocalDateTime serverTime) {
    public Activity withProduct(Product p) {
        return new Activity(id,productId,title,p.name(),p.description(),p.regularPrice(),
            seckillPrice,initialStock,stock,startTime,endTime,status,serverTime);
    }
}
