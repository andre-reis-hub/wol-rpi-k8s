# Terraform - Infraestrutura como codigo

Gerencia recursos de infraestrutura de base do Kubernetes que nao fazem parte do ciclo GitOps do ArgoCD.

## Responsabilidades

- Terraform: StorageClass, infraestrutura de base (criada uma vez)
- ArgoCD: PVs, Deployments, ConfigMaps - ciclo de vida das aplicacoes

## Uso

  terraform init
  terraform plan
  terraform apply

## Estado atual

Recursos gerenciados pelo Terraform:

- kubernetes_storage_class.local_storage (StorageClass local-storage)

## Importar recursos existentes

  terraform import kubernetes_storage_class.local_storage local-storage

## Migracao para AWS

Para migrar para EKS, basta trocar o provider em main.tf para apontar ao endpoint do cluster EKS, usando aws_eks_cluster como data source. Os recursos kubernetes_storage_class permanecem identicos - essa e a grande vantagem do provider kubernetes do Terraform.
