package edu.tju.lab2;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record Order(String id, String requestId, long activityId, String userId,
                    String productName, BigDecimal unitPrice, int quantity,
                    String status, LocalDateTime createdAt) { }
