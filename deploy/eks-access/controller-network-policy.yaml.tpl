apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: aws-load-balancer-controller
  namespace: kube-system
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: aws-load-balancer-controller
  policyTypes: [Ingress, Egress]
  ingress:
    - from:
        - ipBlock:
            cidr: __VPC_CIDR__
      ports:
        - protocol: TCP
          port: 9443
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    - to:
        - ipBlock:
            cidr: __KUBERNETES_SERVICE_IP__/32
      ports:
        - protocol: TCP
          port: 443
    - to:
        - ipBlock:
            cidr: 169.254.170.23/32
      ports:
        - protocol: TCP
          port: 80
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
            except:
              - 10.0.0.0/8
              - 100.64.0.0/10
              - 127.0.0.0/8
              - 169.254.0.0/16
              - 172.16.0.0/12
              - 192.168.0.0/16
      ports:
        - protocol: TCP
          port: 443
