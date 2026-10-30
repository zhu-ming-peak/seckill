package edu.tju.lab2;

public class BusinessException extends RuntimeException {
    final String code;
    final int status;
    public BusinessException(String code, String message, int status) {
        super(message); this.code=code; this.status=status;
    }
}
