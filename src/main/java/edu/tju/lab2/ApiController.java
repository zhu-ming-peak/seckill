package edu.tju.lab2;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Pattern;
import java.util.List;
import java.util.Map;
import org.springframework.validation.annotation.Validated;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@Validated
public class ApiController {
    private final SeckillService service;
    private final JdbcTemplate jdbc;
    private final ProductCache products;
    private final RedisStockGate stockGate;
    public ApiController(SeckillService service,JdbcTemplate jdbc,ProductCache products,RedisStockGate stockGate) {
        this.service=service;this.jdbc=jdbc;this.products=products;this.stockGate=stockGate;
    }
    public record Purchase(
        @Pattern(regexp="[A-Za-z0-9_-]{1,64}",message="用户编号只允许 1–64 位字母、数字、下划线或短横线")
        @jakarta.validation.constraints.NotNull String userId,
        @Pattern(regexp="[A-Za-z0-9_-]{1,64}",message="请求编号格式不正确")
        @jakarta.validation.constraints.NotNull String requestId) { }
    @GetMapping("/health")
    Map<String,String> health() {
        jdbc.queryForObject("SELECT 1",Integer.class);
        return Map.of("status","UP","database","UP","redis",stockGate.ping(),"version","0.2.0-cache","mode",stockGate.enabled?"MYSQL_REDIS":"MYSQL");
    }
    @GetMapping("/api/products/{id}")
    ResponseEntity<Product> product(@PathVariable long id) {
        ProductCache.Lookup result=products.lookup(id);
        return ResponseEntity.ok().header("X-Product-Cache",result.source()).body(result.product());
    }
    @GetMapping("/api/activities") List<Activity> activities() { return service.activities(); }
    @GetMapping("/api/activities/{id}") Activity activity(@PathVariable long id) { return service.activity(id); }
    @PostMapping("/api/activities/{id}/orders")
    Order place(@PathVariable long id,@Valid @RequestBody Purchase purchase) {
        return service.place(id,purchase.userId(),purchase.requestId());
    }
    @GetMapping("/api/orders")
    List<Order> orders(@RequestParam @Pattern(regexp="[A-Za-z0-9_-]{1,64}") String userId) {
        return service.orders(userId);
    }
    @GetMapping("/api/orders/by-request/{requestId}")
    Order result(@PathVariable @Pattern(regexp="[A-Za-z0-9_-]{1,64}") String requestId,
                 @RequestParam @Pattern(regexp="[A-Za-z0-9_-]{1,64}") String userId) {
        return service.result(requestId,userId);
    }
}
