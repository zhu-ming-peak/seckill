package edu.tju.lab2;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.apache.rocketmq.client.consumer.DefaultMQPushConsumer;
import org.apache.rocketmq.client.consumer.listener.ConsumeConcurrentlyStatus;
import org.apache.rocketmq.client.consumer.listener.MessageListenerConcurrently;
import org.apache.rocketmq.client.producer.DefaultMQProducer;
import org.apache.rocketmq.client.producer.SendStatus;
import org.apache.rocketmq.common.consumer.ConsumeFromWhere;
import org.apache.rocketmq.common.message.Message;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name="seckill.mq-enabled",havingValue="true")
public class RocketMqGateway implements SmartLifecycle {
    private final DefaultMQProducer producer;
    private final ObjectMapper json;
    private final AsyncOrderProcessor processor;
    private final RequestMapper requests;
    private final AsyncInventoryReconciler repair;
    private final String namesrv,topic,group;
    private final boolean consumerEnabled;
    private DefaultMQPushConsumer consumer;
    private volatile boolean running;
    public record Payload(String requestId){}
    public RocketMqGateway(ObjectMapper json,AsyncOrderProcessor processor,RequestMapper requests,
        AsyncInventoryReconciler repair,@Value("${seckill.mq-namesrv}")String namesrv,
        @Value("${seckill.mq-topic}")String topic,@Value("${seckill.mq-consumer-group}")String group,
        @Value("${seckill.mq-consumer-enabled:true}")boolean consumerEnabled){
        this.json=json;this.processor=processor;this.requests=requests;this.repair=repair;
        this.namesrv=namesrv;this.topic=topic;this.group=group;this.consumerEnabled=consumerEnabled;
        producer=new DefaultMQProducer("lab2-outbox-producer");producer.setNamesrvAddr(namesrv);
        producer.setInstanceName("lab2-producer-"+UUID.randomUUID());producer.setSendMsgTimeout(3000);
        producer.setRetryTimesWhenSendFailed(0);
    }
    @Override public synchronized void start(){
        try{producer.start();if(consumerEnabled)startConsumer();running=true;}
        catch(Exception e){producer.shutdown();throw new IllegalStateException("RocketMQ client startup failed",e);}
    }
    public synchronized void startConsumer() throws Exception{
        if(consumer!=null)return;
        consumer=new DefaultMQPushConsumer(group);consumer.setNamesrvAddr(namesrv);
        consumer.setInstanceName("lab2-consumer-"+UUID.randomUUID());
        consumer.setConsumeFromWhere(ConsumeFromWhere.CONSUME_FROM_FIRST_OFFSET);
        consumer.setConsumeThreadMin(2);consumer.setConsumeThreadMax(4);consumer.setConsumeMessageBatchMaxSize(1);
        consumer.setMaxReconsumeTimes(3);consumer.subscribe(topic,"*");
        consumer.registerMessageListener((MessageListenerConcurrently)(messages,context)->{
            for(var message:messages){
                try{
                    Payload payload=json.readValue(message.getBody(),Payload.class);
                    RequestRow row=requests.get(payload.requestId());
                    if(row==null){LoggerFactory.getLogger(getClass()).warn("MQ_UNKNOWN_REQUEST id={}",payload.requestId());continue;}
                    processor.process(row.requestId(),row.activityId());
                    try{repair.terminal(row.requestId());}catch(Exception e){LoggerFactory.getLogger(getClass()).warn("MQ_REDIS_REPAIR_PENDING request={}",row.requestId());}
                    LoggerFactory.getLogger(getClass()).info("MQ_CONSUMED request={} message={} redelivery={}",row.requestId(),message.getMsgId(),message.getReconsumeTimes());
                }catch(Exception e){
                    LoggerFactory.getLogger(getClass()).warn("MQ_CONSUME_RETRY message={} type={}",message.getMsgId(),e.getClass().getSimpleName());
                    return ConsumeConcurrentlyStatus.RECONSUME_LATER;
                }
            }
            return ConsumeConcurrentlyStatus.CONSUME_SUCCESS;
        });
        consumer.start();
    }
    public synchronized void stopConsumer(){if(consumer!=null){consumer.shutdown();consumer=null;}}
    public String publish(String id) throws Exception{
        Message message=new Message(topic,"order",id,json.writeValueAsBytes(new Payload(id)));
        var sent=producer.send(message);
        if(sent.getSendStatus()!=SendStatus.SEND_OK)throw new IllegalStateException("MQ status "+sent.getSendStatus());
        LoggerFactory.getLogger(getClass()).info("MQ_SENT request={} message={}",id,sent.getMsgId());
        return sent.getMsgId();
    }
    public boolean clientsRunning(){return running;}
    @Override public synchronized void stop(){stopConsumer();producer.shutdown();running=false;}
    @Override public boolean isRunning(){return running;}
}
