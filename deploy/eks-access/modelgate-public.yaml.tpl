apiVersion: v1
kind: Service
metadata:
  name: modelgate-public
  namespace: modelgate-lab
  labels:
    app.kubernetes.io/name: modelgate
    app.kubernetes.io/component: public-entrypoint
  annotations:
    service.beta.kubernetes.io/aws-load-balancer-type: external
    service.beta.kubernetes.io/aws-load-balancer-nlb-target-type: ip
    service.beta.kubernetes.io/aws-load-balancer-scheme: internet-facing
    service.beta.kubernetes.io/aws-load-balancer-subnets: __PUBLIC_SUBNET_ID__
    service.beta.kubernetes.io/aws-load-balancer-eip-allocations: __EIP_ALLOCATION_ID__
    service.beta.kubernetes.io/aws-load-balancer-healthcheck-protocol: HTTP
    service.beta.kubernetes.io/aws-load-balancer-healthcheck-path: /healthz
    service.beta.kubernetes.io/aws-load-balancer-healthcheck-port: traffic-port
    service.beta.kubernetes.io/aws-load-balancer-attributes: load_balancing.cross_zone.enabled=true
    service.beta.kubernetes.io/aws-load-balancer-target-group-attributes: preserve_client_ip.enabled=true
spec:
  type: LoadBalancer
  loadBalancerClass: service.k8s.aws/nlb
  allocateLoadBalancerNodePorts: false
  externalTrafficPolicy: Cluster
  loadBalancerSourceRanges:
__LOAD_BALANCER_SOURCE_RANGES__
  selector:
    app.kubernetes.io/name: modelgate
  ports:
    - name: http
      protocol: TCP
      port: 80
      targetPort: http
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: modelgate-public
  namespace: modelgate-lab
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: modelgate
  policyTypes: [Ingress]
  ingress:
    - from:
__MODELGATE_INGRESS_IPBLOCKS__
      ports:
        - protocol: TCP
          port: 8080
