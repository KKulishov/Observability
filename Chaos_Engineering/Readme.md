## simple example for chaosblade 

[chaosblade](https://chaosblade.io/en/) 
[github](https://github.com/chaosblade-io/chaosblade)


## example CPU container throttling

simple example kubernetes yaml for namespace bookinfo , label  app=productpage

timeout 5 minut 

cpu-percent set from request&limit cpu

[kubernetest_cpu_yaml](./cpu_container/cpu-container.yaml)


or cli blade

```sh
blade create cpu load --cpu-percent 70 --timeout 300
```

[docs_cpu](https://chaosblade.io/en/docs/experiment-types/k8s/container/blade_create_k8s_container-cpu)

degradation of service SRE metrics 

## example MEMORY used container 

simple example kubernetes yaml for namespace bookinfo , label  app=productpage

timeout 5 minut 


[kubernetest_memory_yaml](./mem_container/mem_container.yaml)

or cli blade

```
blade create mem load --mode ram --mem-percent 95 --timeout 300
```

degradation of service SRE metrics 

## DNS trap 

Changing the DNS name inside the resolver container . [Trap](./dns/dns_trap.yaml)

Lost dns packets [precent](./dns/dns_down.yaml)

## Network 

[losst](./net/losst.yaml) 
[drop](./net/drop.yaml) 
[latency](./net/latency.yaml) 

for pattern testing retray/circuit breaker/ timeout 

## Kill process

check SIGTERM signal and works gracefullshutdown and work service 5xx 

## IOps In/Out in 

[example](https://chaosblade.io/en/docs/experiment-types/k8s/pod/blade_create_k8s_pod-IO)




## ToDo check [Java](https://chaosblade.io/en/docs/experiment-types/application/jvm/) 

Simulating Memory Overflow

```sh
blade c jvm oom --area HEAP --wild-mode true --pid\$JAVA_PID 
```

Simulate full CPU load of Java process

```sh
blade c jvm cfl --process tomcat
```

Simulate Class Method Invocation Delay


```sh
blade c jvm delay --time 4000 --classname=com.example.controller.DubboController --methodname=sayHello --process tomcat
```

