package edu.tju.lab2;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record Activity(long id, long productId, String title, String productName,
                       String description, BigDecimal regularPrice, BigDecimal seckillPrice,
                       int initialStock, int stock, LocalDateTime startTime,
                       LocalDateTime endTime, String status, LocalDateTime serverTime) {
    public String getState() {
        if (!"ACTIVE".equals(status)) return "DISABLED";
        if (serverTime.isBefore(startTime)) return "UPCOMING";
        if (!serverTime.isBefore(endTime)) return "ENDED";
        if (stock <= 0) return "SOLD_OUT";
        return "OPEN";
    }
}
