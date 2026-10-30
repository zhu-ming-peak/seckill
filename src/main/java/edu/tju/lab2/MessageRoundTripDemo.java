package edu.tju.lab2;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import org.apache.rocketmq.client.consumer.DefaultMQPushConsumer;
import org.apache.rocketmq.client.consumer.listener.*;
import org.apache.rocketmq.client.producer.DefaultMQProducer;
import org.apache.rocketmq.common.consumer.ConsumeFromWhere;
import org.apache.rocketmq.common.message.Message;

/** 独立生产者/消费者示例，不启动 Spring、MySQL 或 Redis。 */
public class MessageRoundTripDemo {
    public static void run() throws Exception{
        String run=UUID.randomUUID().toString(),topic="Lab2MessageDemo";
        String namesrv=System.getenv().getOrDefault("ROCKETMQ_NAMESRV_ADDR","127.0.0.1:9876");
        CountDownLatch latch=new CountDownLatch(3);Set<String> received=ConcurrentHashMap.newKeySet();
        DefaultMQPushConsumer consumer=new DefaultMQPushConsumer("lab2-demo-"+run);
        DefaultMQProducer producer=new DefaultMQProducer("lab2-demo-producer-"+run);
        try{
            consumer.setNamesrvAddr(namesrv);consumer.setConsumeFromWhere(ConsumeFromWhere.CONSUME_FROM_FIRST_OFFSET);
            consumer.setConsumeThreadMin(1);consumer.setConsumeThreadMax(2);consumer.subscribe(topic,"*");
            consumer.registerMessageListener((MessageListenerConcurrently)(messages,context)->{
                for(var message:messages)if(message.getKeys().startsWith(run)&&received.add(message.getKeys())){
                    System.out.println("CONSUMED key="+message.getKeys()+" messageId="+message.getMsgId()+" body="+new String(message.getBody(),StandardCharsets.UTF_8));latch.countDown();
                }
                return ConsumeConcurrentlyStatus.CONSUME_SUCCESS;
            });
            consumer.start();producer.setNamesrvAddr(namesrv);producer.start();
            for(int i=1;i<=3;i++){
                String key=run+"-"+i;
                var result=producer.send(new Message(topic,"demo",key,("lab2-message-"+i).getBytes(StandardCharsets.UTF_8)));
                System.out.println("PRODUCED key="+key+" messageId="+result.getMsgId()+" status="+result.getSendStatus());
            }
            if(!latch.await(30,TimeUnit.SECONDS))throw new IllegalStateException("Message verification timed out");
            System.out.println("ROUND_TRIP_VERIFIED count="+received.size());
        }finally{producer.shutdown();consumer.shutdown();}
    }
}
