package edu.tju.lab2;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@org.springframework.scheduling.annotation.EnableScheduling
public class SeckillApplication {
    public static void main(String[] args) throws Exception {
        if(args.length>0&&"mq-demo".equals(args[0])){MessageRoundTripDemo.run();return;}
        SpringApplication.run(SeckillApplication.class, args);
    }
}
