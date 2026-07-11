# metrics-server (kubectl top + dashboards de recursos)

## Instalar
```
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

## Patch OBRIGATORIO (cluster kubeadm com cert self-signed)
Sem isso o metrics-server fica 0/1 (nao Ready):
```
kubectl patch deployment metrics-server -n kube-system --type=json \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
```

Depois: kubectl top nodes / kubectl top pods funcionam.
