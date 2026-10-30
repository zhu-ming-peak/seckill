package edu.tju.lab2;

import jakarta.validation.ConstraintViolationException;
import java.util.Map;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.PessimisticLockingFailureException;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.http.converter.HttpMessageNotReadableException;

@RestControllerAdvice
public class ApiErrors {
    @ExceptionHandler({org.springframework.data.redis.RedisConnectionFailureException.class,
        org.springframework.data.redis.RedisSystemException.class,
        org.springframework.dao.QueryTimeoutException.class})
    ResponseEntity<?> redisUnavailable(Exception e) {return response(503,"CACHE_UNAVAILABLE","库存服务暂时不可用，请保留原请求编号重试");}
    @ExceptionHandler(BusinessException.class)
    ResponseEntity<?> business(BusinessException e) { return response(e.status,e.code,e.getMessage()); }
    @ExceptionHandler(DuplicateKeyException.class)
    ResponseEntity<?> duplicate(DuplicateKeyException e) { return response(409,"DUPLICATE_REQUEST","购买或请求编号重复，请查询原订单"); }
    @ExceptionHandler(PessimisticLockingFailureException.class)
    ResponseEntity<?> busy(PessimisticLockingFailureException e) { return response(503,"BUSY","系统繁忙，请使用原请求编号重试"); }
    @ExceptionHandler({MethodArgumentNotValidException.class,ConstraintViolationException.class,
        HandlerMethodValidationException.class,MethodArgumentTypeMismatchException.class,HttpMessageNotReadableException.class})
    ResponseEntity<?> invalid(Exception e) { return response(400,"INVALID_ARGUMENT","请检查活动编号、用户编号和请求编号"); }
    private ResponseEntity<?> response(int status,String code,String message) {
        return ResponseEntity.status(status).body(Map.of("code",code,"message",message));
    }
}
