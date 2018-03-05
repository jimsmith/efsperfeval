import argparse
import boto3
import botocore
import pprint
import subprocess
import sys


def stack_status(client, stack_name):
    desc = client.describe_stacks(StackName=stack_name)
    return desc["Stacks"][0]["StackStatus"]

def run_on_hosts(command_input, timeout=None, failure_expected=False):
    args = ["pssh", "-h", "host.list.public",
            "-l", "ec2-user",
            "-o", "log", "-e", "errlog",
            "-O", "StrictHostKeyChecking=no",
            "-I"]
    if timeout:
        args += ["-t", str(timeout)]
    p = subprocess.Popen(args,
        stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    command_stdout, command_stderr = p.communicate(input=command_input.encode("utf-8"))
    if p.returncode and not failure_expected:
        print(command_stdout)
        print(command_stderr)
        raise
    else:
        print("success")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cloud configuration to evaluate a file system")
    subparsers = parser.add_subparsers(dest="subparser_name", help="sub-command help")

    parser_status = subparsers.add_parser("status", help="Query Cloud Formation stack status")
    parser_status.add_argument("--stack-name", required=True,
        help="name of this Cloud Formation stack")

    parser_deploy = subparsers.add_parser("update", help="Configure a Cloud Formation stack")
    parser_deploy.add_argument("--stack-name", required=True,
        help="name of this Cloud Formation stack")
    parser_deploy.add_argument("--ssh-key-name", required=True,
        help="name of the ssh key used to log into ec2 instances")
    parser_deploy.add_argument("--efs-file-system-id", required=True,
        help="identifier for the file system")
    parser_deploy.add_argument("--az-scale-a", type=int, default=1,
        help="number of test instances in availability zone a")
    parser_deploy.add_argument("--az-scale-rest", type=int, default=0,
        help="number of test instances in availability zones b-f")

    parser_instances = subparsers.add_parser("instances", help="Query test host instances")
    parser_instances.add_argument("--stack-name", required=True,
        help="name of this Cloud Formation stack")

    parser_instanceconfig = subparsers.add_parser("instanceconfig",
        help="Update instances with test software")
    parser_instanceconfig.add_argument("--stack-name", required=True,
        help="name of this Cloud Formation stack")
    parser_instanceconfig.add_argument("--efs-file-system-id", required=True,
        help="identifier for the file system")

    parser_instanceconfig = subparsers.add_parser("remove",
        help="Clean up Cloud Formation stack")
    parser_instanceconfig.add_argument("--stack-name", required=True,
        help="name of this Cloud Formation stack")

    args = parser.parse_args()

    stack_name = args.stack_name

    if args.subparser_name == "status":
        client = boto3.client("cloudformation")
        print(stack_status(client, stack_name))
    elif args.subparser_name == "update":
        client = boto3.client("cloudformation")
        with open("config_efstest.json") as f:
            template_body = f.read()
        stack_kwargs = {
            "StackName": stack_name,
            "TemplateBody": template_body,
            "Parameters": [
                {
                    "ParameterKey": "KeyName",
                    "ParameterValue": args.ssh_key_name
                },
                {
                    "ParameterKey": "FileSystem",
                    "ParameterValue": args.efs_file_system_id
                },
                {
                    "ParameterKey": "AzScaleA",
                    "ParameterValue": str(args.az_scale_a)
                },
                {
                    "ParameterKey": "PerAzScaleRest",
                    "ParameterValue": str(args.az_scale_rest)
                }
            ],
            "Capabilities": ["CAPABILITY_IAM"]
        }

        # check to see whether this stack exists already
        stack_exists = True
        try:
            ds = client.describe_stacks(StackName=stack_name)
        except botocore.exceptions.ClientError as ex:
            if str(ex).endswith("does not exist"):
                stack_exists = False
            else:
                raise ex
        if stack_exists:
            client.update_stack(**stack_kwargs)
        else:
            client.create_stack(**stack_kwargs)
    elif args.subparser_name == "instances":
        ec2 = boto3.client("ec2")
        # TODO - this isn't really the best way to filter, should create a tag
        filters = [{"Name":"tag:aws:cloudformation:stack-name", "Values":[stack_name]},
            {'Name':'instance-type', 'Values':['m5.large','m4.large']},
            {'Name':'instance-state-name', 'Values':['running']}]
        r = ec2.describe_instances(Filters=filters)
        instances = list([instance for reservation in r["Reservations"] for instance in reservation["Instances"]])
        with open("host.list.private", "w") as f:
            for instance in instances:
                f.write("%s\n" % instance["PrivateIpAddress"])
        with open("host.list.public", "w") as f:
            for instance in instances:
                f.write("%s\n" % instance["PublicIpAddress"])
        with open("host.list.subnets", "w") as f:
            for instance in instances:
                f.write("%s %s %s\n" % (instance["PrivateIpAddress"], instance["PublicIpAddress"], instance["SubnetId"]))
        print("have %d load test instances" % len(instances))
        print("output to host.list.{public,private,subnets}")
    elif args.subparser_name == "instanceconfig":
        # TODO gen instances if not already there
        install_command = (
            "if [ ! -d /efs ]; then\n"
            "    sudo mkdir -p /efs\n"
            "    sudo mount -t nfs4 \\\n"
            "    -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2 \\\n"
            "    %s.efs.us-east-1.amazonaws.com:/ /efs\n"
            "fi"
        ) % args.efs_file_system_id
        print("running mount command")
        run_on_hosts(install_command)

        install_fio_command = (
            "if [ ! -e /usr/local/bin/fio ]; then\n"
            "    sudo yum install -y libaio-devel git make glibc-devel gcc patch\n"
            "    git clone https://github.com/axboe/fio\n"
            "    cd fio\n"
            "    git checkout fio-3.4\n"
            "    ./configure\n"
            "    make\n"
            "    sudo make install\n"
            "fi"
        )
        print("running fio installation")
        run_on_hosts(install_fio_command, timeout=300)

        start_fio_command = (
            "killall -9 fio\n"
            "nohup /usr/local/bin/fio --server 2>&1 > server.log"
        )
        print("running fio server start")
        run_on_hosts(start_fio_command, timeout=2, failure_expected=True)
    elif args.subparser_name == "remove":
        client = boto3.client("cloudformation")
        client.delete_stack(**{ "StackName": stack_name })
        print("deleted stack %s" % stack_name)
    else:
        raise
