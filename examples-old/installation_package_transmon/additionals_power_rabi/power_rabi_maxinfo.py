from qm import SimulationConfig
from qm.qua import *
from qm import LoopbackInterface
from qm.QuantumMachinesManager import QuantumMachinesManager
from configuration import *
import matplotlib.pyplot as plt
import numpy as np

################################
# Open quantum machine manager #
################################

qmm = QuantumMachinesManager()

########################
# Open quantum machine #
########################

qm = qmm.open_qm(config)

###################
# The QUA program #
###################

n_avg = 1000  # number of averages

cooldown_time = 50000 // 4  # qubit decay time

a_min = 0.0
a_max = 1.0
da = 0.1

amps = np.arange(a_min, a_max + da / 2, da)  # + da/2 to add a_max to amplitudes


with program() as power_rabi:

    # Declare QUA variables
    ###################
    n = declare(int)  # variable for average loop
    n_st = declare_stream()  # stream for 'n'
    a = declare(fixed)  # variable for amps sweep
    I = declare(fixed)  # demodulated and integrated signal
    Q = declare(fixed)  # demodulated and integrated signal
    d_st = declare_stream()  # stream for d
    d_I = declare(fixed, value=1.0)  # I_e - I_g / np.sqrt(dI**2 + dQ**2), projection to the unitary vector
    d_Q = declare(fixed, value=1.0)  # Q_e - Q_g / np.sqrt(dI**2 + dQ**2), projection to the unitary vector
    d = declare(fixed)

    # Pulse sequence
    ################
    with for_(n, 0, n < n_avg, n + 1):

        with for_(
            a, a_min, a < a_max + da / 2, a + da
        ):  # Notice it's + da/2 to include a_max (This is only for fixed!)
            wait(cooldown_time, "qubit")  # wait for qubit to decay
            play("gaussian" * amp(a), "qubit")  # play gaussian pulse with variable amplitude
            align("qubit", "resonator")
            measure(
                "readout",
                "resonator",
                None,
                dual_demod.full("cos", "out1", "sin", "out2", I),
                dual_demod.full("minus_sin", "out1", "cos", "out2", Q),
            )
            assign(d, I * d_I + Q * d_Q)  # dot product of measured I,Q with d_I,d_Q
            save(d, d_st)  # save dot product to stream
        save(n, n_st)

    # Stream processing
    ###################
    with stream_processing():
        n_st.save("iteration")
        d_st.buffer(len(amps)).average().save("d")

#######################
# Simulate or execute #
#######################

simulate = True

if simulate:
    # simulation properties
    simulate_config = SimulationConfig(
        duration=100000,
        simulation_interface=LoopbackInterface(([("con1", 1, "con1", 1)])),
    )
    job = qmm.simulate(config, power_rabi, simulate_config)  # do simulation with qmm
    job.get_simulated_samples().con1.plot()  # visualize played pulses

else:
    job = qm.execute(power_rabi)  # execute QUA program

    res_handles = job.result_handles  # get access to handles
    d_handle = res_handles.get("d")
    d_handle.wait_for_values(1)
    iteration_handle = res_handles.get("iteration")
    iteration_handle.wait_for_values(1)

    while res_handles.is_processing():
        try:
            d = d_handle.fetch_all()
            iteration = iteration_handle.fetch_all() + 1
            plt.title("Power Rabi")
            plt.plot(amps, d)
            plt.xlabel("Amps")
            plt.ylabel("demod signal [a.u.]")
            plt.pause(0.1)
            plt.clf()
            print(iteration)

        except Exception as e:
            pass

    d = d_handle.fetch_all()
    plt.title("resonator spectroscopy analysis")
    plt.plot(amps, d)
    plt.xlabel("Amps")
    plt.ylabel("demod signal [a.u.]")
