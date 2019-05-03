'''
Created on Apr 27, 2019

@author: timothysaucer
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
    kernel = sml.Kernel.CreateKernelInCurrentThread(True, 12121)
    print('Listening on port {}'.format(kernel.GetListenerPort()))
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
    x_pos = gym_id.CreateFloatWME('x-position', 0.)
    y_pos = gym_id.CreateFloatWME('y-position', 0.)
    x_vel = gym_id.CreateFloatWME('x-velocity', 0.)
    y_vel = gym_id.CreateFloatWME('y-velocity', 0.)
    ang_pos = gym_id.CreateFloatWME('orientation-angle', 0.)
    ang_vel = gym_id.CreateFloatWME('orientation-angular-velocity', 0.)
    left_lander = gym_id.CreateStringWME('left-pad-contact', '*NGS_NO*')
    right_lander = gym_id.CreateStringWME('right-pad-contact', '*NGS_NO*')

    return (x_pos, y_pos, x_vel, y_vel, ang_pos, ang_vel, left_lander, right_lander)

def has_contact(pad_value):
    return pad_value > 0.5

def update_input_wmes(observation):
    global input_wmes
    (x_pos, y_pos, x_vel, y_vel, ang_pos, ang_vel, left_lander, right_lander) = input_wmes
    
    x_pos.Update(float(observation[0]))
    y_pos.Update(float(observation[1]))
    x_vel.Update(float(observation[2]))
    y_vel.Update(float(observation[3]))
    ang_pos.Update(float(observation[4]))
    ang_vel.Update(float(observation[5]))
    left_lander.Update('*YES*' if has_contact(observation[6]) else '*NO*')
    right_lander.Update('*YES*' if has_contact(observation[7]) else '*NO*')

if __name__ == "__main__":
    # Create the user input thread and queue for return commands
    queue_user_cmds = queue.Queue()
    user_cmd_thread = CliThread(queue_user_cmds)
    user_cmd_thread.start()
    
    # Create the soar agent
    kernel = create_kernel()
    agent = create_agent(kernel, "agent")
    register_print_callback(kernel, agent, callback_print_message, None)
    
    # Cannot just execute this in the source file because the library doesn't load fast enough.
    # We might even need to put in a delay or verify we got a response that it was loaded.
    
    print(agent.ExecuteCommandLine("rl --set learning on"))
    print(agent.ExecuteCommandLine("indifferent-selection --epsilon-greedy"))

    print(agent.ExecuteCommandLine("soar tcl on"))
    
    input_wmes = create_input_wmes(agent)
    
    # Create the gym environment
    gym_env = gym.make('LunarLander-v2')
    observation = gym_env.reset()
    update_input_wmes(observation)
    
    step_num = 0
    print('Step, x-pos, y-pos, x-vel, y-vel, ang, ang-vel, left-pad, right-pad')
    print('{}, {}, {}, {}, {}, {}, {}, {}, {}'.format(step_num, observation[0], observation[1], observation[2], observation[3], observation[4], observation[5], has_contact(observation[6]), has_contact(observation[0])))
    
    print(agent.ExecuteCommandLine("source soar/load.soar"))
     
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
        is_paused = True
        if is_paused:
            continue
         
        kernel.CheckForIncomingCommands()
        kernel.RunAllAgents(1)
        move_cmd = get_move_command(agent)
         
        if move_cmd is not None:
            observation, reward, done, info = gym_env.step(move_cmd)
             
            step_num = step_num + 1
            update_input_wmes(observation)
             
            print('{}, {}, {}, {}, {}, {}, {}, {}, {}'.format(step_num, observation[0], observation[1], observation[2], observation[3], observation[4], observation[5], has_contact(observation[6]), has_contact(observation[0])))
             
            if done:
                if step_num >= 195:
                    if last_run_passed:
                        num_consecutive_passes = num_consecutive_passes + 1
                    else:
                        last_run_passed = True
                        num_consecutive_passes = 1
                else:
                    last_run_passed = False
                     
                print('Episode: ', episode_num, "Number of steps: ", step_num, 'Number of consecutive passes: ', num_consecutive_passes)
                episode_num = episode_num + 1
                 
                step_num = 0
                gym_env.reset()
                agent.ExecuteCommandLine("init-soar")

    
    gym_env.close()
    kernel.DestroyAgent(agent)
    kernel.Shutdown()
    del kernel
