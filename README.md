# EFS Performance Evaluation

This repository contains scripts to aid in understanding the performance of
Amazon's Elastic File System (EFS).

## Environment Setup

Set the following environment variables before proceeding with further steps:.
```
export AWS_DEFAULT_REGION=...
export EC2_KEY_PAIR=...
export EFS_EVAL_FILE_SYSTEM_ID=...
export EFS_EVAL_STACK_NAME=...
```

`AWS_DEFAULT_REGION` should be your preferred region, e.g., us-west-2.
`EC2_KEY_PAIR` should be the name of the ssh key used to log into EC2.
This should match a `KeyName` as returned by `aws ec2 describe-key-pairs`.
`EFS_EVAL_FILE_SYSTEM_ID` should match the file system identifier of the EFS
under test. It should look something like `fs-12594a6d`.
`EFS_EVAL_STACK_NAME` is a name of your choice, e.g., `efs-test`.

If you are using a non-default profile configure it as:
```
export AWS_DEFAULT_PROFILE=...
```
setting `AWS_DEFAULT_PROFILE` to a the heading of a section within your
`~/.aws/credentials` file.

## Configuring a cluster

We use scripts that control AWS Cloud Formation to configure resources for the
experiment.

```
python3 clusterconfig.py update \
    --stack-name=$EFS_EVAL_STACK_NAME \
    --ssh-key-name=$EC2_KEY_PAIR \
    --efs-file-system-id=$EFS_EVAL_FILE_SYSTEM_ID \
    --az-scale-a=4 \
    --az-scale-rest=0
```

You can check on the status of the configuration as follows:
```
python3 clusterconfig.py status --stack-name=$EFS_EVAL_STACK_NAME
```

Configure each test instance. This command will install the necessary software.
```
python3 clusterconfig.py instances \
    --stack-name=$EFS_EVAL_STACK_NAME
```

Generate a list of instances.
```
python3 clusterconfig.py instanceconfig \
    --stack-name=$EFS_EVAL_STACK_NAME \
    --efs-file-system-id=$EFS_EVAL_FILE_SYSTEM_ID
```


When finished you can clean up the resources
```
python3 clusterconfig.py remove \
    --stack-name=$EFS_EVAL_STACK_NAME
```

## Running Experiments

This command should be run on the control server
```
python3 scan_fio.py \
    --results /scanres \
    --block-sizes=4K,32K,256K \
    --modes=randread,randwrite,randrw \
    --io-depths=4,8 \
    --num-clients=2,4 \
    --num-iterations=2 \
    --unique-filenames
```

See results with
```
python3 analyze.py \
    --results /scanres
```
