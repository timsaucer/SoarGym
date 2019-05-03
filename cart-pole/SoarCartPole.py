'''
Created on Apr 27, 2019

@author: timothysaucer

Based on:

https://soar.eecs.umich.edu/articles/downloads/examples-and-unsupported/183-python-interface-example
http://gym.openai.com/docs/

'''
#!/usr/bin/env python2.7

from os import environ as env
import sys
import gym
import threading
import queue

if "DYLD_LIBRARY_PATH" in env:
    LIB_PATH = env["DYLD_LIBRARY_PATH"]
elif "LD_LIBRARY_PATH" in env:
    LIB_PATH = env["LD_LIBRARY_PATH"]
else:
    print("Soar LIBRARY_PATH environment variable not set; quitting")
    exit(1)
sys.path.append(LIB_PATH)
import Python_sml_ClientInterface as sml

last_run_passed = False
num_consecutive_passes = 0
is_paused = False
episode_num = 1

class CliThread(threading.Thread):

    def __init__(self, q_main_thread):
        self.queue_main = q_main_thread
        threading.Thread.__init__(self)

    def run(self):
        cmd = "None"
        while cmd not in ("exit", "quit"):
            cmd = raw_input("soar> ")
            self.queue_main.put(cmd)

def create_kernel():
    kernel = sml.Kernel.CreateKernelInCurrentThread()
    if not kernel or kernel.HadError():
        print("Error creating kernel: " + kernel.GetLastErrorDescription())
        exit(1)
    return kernel

def create_agent(kernel, name):
    agent = kernel.CreateAgent("agent")
    if not agent:
        print("Error creating agent: " + kernel.GetLastErrorDescription())
        exit(1)
    return agent

def parse_output_commands(agent, structure):
    commands = {}
    mapping = {}
    for cmd in range(0, agent.GetNumberCommands()):
        error = False
        command = agent.GetCommand(cmd)
        cmd_name = command.GetCommandName()
        if cmd_name in structure:
            parameters = {}
            for param_name in structure[cmd_name]:
                param_value = command.GetParameterValue(param_name)
                if param_value:
                    parameters[param_name] = param_value
            if not error:
                commands[cmd_name] = parameters
                mapping[cmd_name] = command
        else:
            error = True
        if error:
            command.AddStatusError()
    return commands, mapping

# callback registry

def register_print_callback(kernel, agent, function, user_data=None):
    agent.RegisterForPrintEvent(sml.smlEVENT_PRINT, function, user_data)

def get_move_command(agent):
    output_command_list = { 'move-cart': ['direction'] }

    if agent.Commands():
        (commands, mapping) = parse_output_commands(agent, output_command_list)
        
        move_cart_cmd = commands['move-cart']
        direction = move_cart_cmd['direction']
        
        mapping['move-cart'].CreateStringWME('status', 'complete')
        
        if direction == 'left':
            return 0
        else:
            return 1
    
    return None

def callback_print_message(mid, user_data, agent, message):
    print(message.strip())

def create_input_wmes(agent):
    gym_id = agent.GetInputLink().CreateIdWME('gym')
    cart_pos = gym_id.CreateFloatWME('cart-position', 0.)
    cart_vel = gym_id.CreateFloatWME('cart-velocity', 0.)
    pole_pos = gym_id.CreateFloatWME('pole-angle', 0.)
    pole_vel = gym_id.CreateFloatWME('pole-tip-velocity', 0.)

    return (cart_pos, cart_vel, pole_pos, pole_vel)

def has_contact(pad_value):
    return pad_value > 0.5

def update_input_wmes(observation):
    global input_wmes
    (cart_pos, cart_vel, pole_pos, pole_vel) = input_wmes
    
    cart_pos.Update(observation[0])
    cart_vel.Update(observation[1])
    pole_pos.Update(observation[2])
    pole_vel.Update(observation[3])

if __name__ == "__main__":
    # Create the user input thread and queue for return commands
    queue_user_cmds = queue.Queue()
    user_cmd_thread = CliThread(queue_user_cmds)
    user_cmd_thread.start()
    
    # Create the soar agent
    kernel = create_kernel()
    agent = create_agent(kernel, "agent")
    register_print_callback(kernel, agent, callback_print_message, None)
    
    # Create the gym environment
    gym_env = gym.make('CartPole-v0')
    observation = gym_env.reset()
    
    input_wmes = create_input_wmes(agent)
    update_input_wmes(observation)
    
    step_num = 0
    
    print(agent.ExecuteCommandLine("source cart-pole.soar"))
    
    while True:
        gym_env.render()
        
        try:
            user_cmd = queue_user_cmds.get(False)
        except queue.Empty:
            pass
        else:
            if user_cmd in ("exit", "quit"):
                break
            elif user_cmd == "pause":
                is_paused = True
            elif user_cmd == "continue":
                is_paused = False
            else:
                print(agent.ExecuteCommandLine(user_cmd).strip())
        
        if is_paused:
            continue
        
        kernel.RunAllAgents(1)
        move_cmd = get_move_command(agent)
        
        if move_cmd is not None:
            observation, reward, done, info = gym_env.step(move_cmd)
            
            step_num = step_num + 1
            update_input_wmes(observation)
            
#            print(step_num, observation)
            
            if done:
                if step_num >= 195:
                    if last_run_passed:
                        num_consecutive_passes = num_consecutive_passes + 1
                    else:
                        last_run_passed = True
                        num_consecutive_passes = 1
                else:
                    last_run_passed = False
                    num_consecutive_passes = 0
                    
                print('Episode, {}, Number of steps, {}, Number of consecutive passes, {}'.format(episode_num, step_num, num_consecutive_passes))
#                print('Episode: ', episode_num, "Number of steps: ", step_num, 'Number of consecutive passes: ', num_consecutive_passes)
                episode_num = episode_num + 1
                
                step_num = 0
                gym_env.reset()
                agent.ExecuteCommandLine("init-soar")

    gym_env.close()
    kernel.DestroyAgent(agent)
    kernel.Shutdown()
    del kernel
