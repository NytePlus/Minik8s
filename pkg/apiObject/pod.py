import docker
import platform

class STATUS():
    STOPPED = 'STOPPED'
    RUNNING = 'RUNNING'
    KILLED = 'KILLED'

class Pod():
    def __init__(self, config):
        self.config = config
        self.status = STATUS.RUNNING
        print(f'[INFO]Pod init, status: {self.status}')
        
        if platform == "Windows":
            self.client = docker.DockerClient(
                base_url='npipe:////./pipe/docker_engine',
                version='1.25',
                timeout=5
            )
        else:
            self.client = docker.DockerClient(
                base_url='unix://var/run/docker.sock',
                version='1.25',
                timeout=5
            )
        # print(f'[INFO]enter docker client, base_url: {self.client.base_url}')
        print(f"config: {self.config}")
        self.client.networks.prune()
        print(f"labels: {self.config.labels}")

        # --- 不使用overlay网络 ---
        # self.network = self.client.networks.create(name = 'network_' + self.config.namespace, driver='bridge')
        # self.containers = [self.client.containers.run(image = 'busybox', name = 'pause', detach = True,
        #                            command = ['sh', '-c', 'echo [INFO]pod network init. && sleep 3600'],
        #                            network = self.network.name)]

        # --- 使用overlay网络 ---
        pause_docker_name = "pause_" + self.config.namespace + "_" + self.config.name
        
        self.containers = [self.client.containers.run(image = 'busybox', name = pause_docker_name, detach = True,
                                   command = ['sh', '-c', 'echo [INFO]pod network init. && sleep 3600'],
                                   network = self.config.overlay_name)]
        
        print(f'[INFO]Pod init, pause container: {self.containers[0].name}')
        print(f"container num: {len(self.config.containers)}")
        for container in self.config.containers:
            print(f'[INFO]Pod init, container: {container.name}')
            print(f'[INFO]Pod init, container args: {container.dockerapi_args()}')
            print(f'[INFO]pause_docker_name: {pause_docker_name}')
            
            self.containers.append(self.client.containers.run(**container.dockerapi_args(),
            detach = True, network_mode = f'container:{pause_docker_name}'))
            
            print(f'[INFO]container {container.name} created, id: {self.containers[-1].id}')

    def start(self):
        for container in self.containers:
            self.client.api.start(container.id)
        self.status = STATUS.RUNNING

    def stop(self):
        for container in self.containers:
            self.client.api.stop(container.id)
        self.status = STATUS.STOPPED

    def kill(self):
        for container in self.containers:
            self.client.api.kill(container.id)
        self.status = STATUS.KILLED

    def restart_crash(self):
        for container in self.containers:
            container.reload()
            if container.status == 'exited' and container.attrs['State']['ExitCode'] != 0:
                print(f'[INFO]restart abnormally exited container {container.name}')
                self.client.api.restart(container.id)

    def restart(self):
        for container in self.containers:
            self.client.api.restart(container.id)
        self.status = STATUS.RUNNING

    def remove(self):
        for container in self.containers:
            self.client.api.remove_container(container.id)

if __name__ == '__main__':
    print('[INFO]Testing Pod.')
    
    import yaml
    import requests
    from pkg.config.podConfig import PodConfig
    from pkg.config.uriConfig import URIConfig
    from pkg.config.globalConfig import GlobalConfig
    import os
    config = GlobalConfig()
    # test_file = "pod-for-rs-1.yaml"
    # test_file = "pod-1.yaml"
    test_file = "pod-1 copy.yaml"
    test_yaml = os.path.join(config.TEST_FILE_PATH, test_file)
    # test_yaml = os.path.join(config.TEST_FILE_PATH, 'pod-for-rs-1.yaml')
    print(f'[INFO]使用{test_file}作为测试配置，测试Pod的创建和删除。目前没有使用volume绑定')
    # print(f'[INFO]请求地址: {test_yaml}')
    with open(test_yaml, 'r', encoding='utf-8') as file:
        data = yaml.safe_load(file)

    dist = True
    if dist:
        uri = URIConfig.PREFIX + URIConfig.POD_SPEC_URL.format(
            namespace= data['metadata']['namespace'], name = data['metadata']['name'])
        print(f'[INFO]请求地址: {uri}')
        # podConfig = PodConfig(data)
        # pod = Pod(podConfig)
        # pod.start()
        print(f"[INFO]request data: {data}")
        response = requests.post(uri, json=data)
        print(response)
        
        # 测试pod的获取
        
        uri = URIConfig.PREFIX + URIConfig.POD_SPEC_URL.format(
            namespace= data['metadata']['namespace'], name = data['metadata']['name'])
        print(f'[INFO]请求地址: {uri}')
        response = requests.get(uri)
        print(f'[INFO]获取pod的返回值: {response}')
        # response_config = PodConfig(response.json())
        # response_config = response
        # print(f"pod.label.app: {response_config.get_app_label()},pod.label.env: {response_config.get_env_label()}")
    else:
        podConfig = PodConfig(data)
        pod = Pod(podConfig)
        print(f'[INFO]初始化Pod，status: {pod.status}')
        pod.stop()
        print(f'[INFO]关闭Pod，status: {pod.status}')
        pod.start()
        print(f'[INFO]启动Pod，status: {pod.status}')
        pod.stop()
        print(f'[INFO]关闭Pod，status: {pod.status}')
        pod.remove()
        print(f'[INFO]Pod删除，可以在本地docker desktop查看，容器已经被删除')