package edu.tju.lab2;
import java.math.BigDecimal;
import java.time.LocalDateTime;
public record RequestRow(String requestId,long activityId,String userId,String token,
    String productName,BigDecimal acceptedPrice,String state,String failureCode,String orderId,
    LocalDateTime acceptedAt,LocalDateTime updatedAt,int sendCount,LocalDateTime nextSendAt,
    String lastMessageId,int processingAttempts,int redisDone) { }
