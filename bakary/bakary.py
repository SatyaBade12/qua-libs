"""bakary.py: Framework to generate arbitrary waveforms to be played into QUA program
Author: Arthur Strauss - Quantum Machines
Created: 23/02/2021
"""

from typing import Set, List, Union
import numpy as np
from qm import qua
import copy


def baking(config, padding_method="right"):
    return Baking(config, padding_method)


class Baking:

    def __init__(self, config, padding_method="right"):
        self._config = config
        self._padding_method = padding_method
        self._local_config = copy.deepcopy(config)
        self._samples_dict, self._qe_dict = self._init_dict()
        self._ctr = self._get_baking_index()  # unique name counter

    def __enter__(self):
        return self

    def _get_baking_index(self):
        index = 0
        max_index = 0
        for qe in self._config["elements"].keys():
            for op in self._config["elements"][qe]["operations"]:
                if op.find("baked") != -1:
                    index += 1
            if max_index < index:
                max_index = index
                index = 0
        return max_index

    def _init_dict(self):
        sample_dict = {}
        qe_dict = {}
        for qe in self._config["elements"].keys():
            if "mixInputs" in self._local_config["elements"][qe]:
                sample_dict[qe] = {"I": [],
                                   "Q": []}
                qe_dict[qe] = {"time": 0,
                               "phase": 0,
                               "time_track": 0,
                               "phase_track": [0]
                               }
            elif "singleInput" in self._local_config["elements"][qe]:
                sample_dict[qe] = []
                qe_dict[qe] = {"time": 0,
                               "time_track": 0}
        return sample_dict, qe_dict

    def __exit__(self, exc_type, exc_value, exc_traceback):
        """
        Updates the configuration dictionary upon exit
        """
        if exc_type:
            return

        elements = self._local_config["elements"]
        for qe in elements:
            wait_duration = 0  # Stores the duration that has to be padded with 0s to make a valid sample for QUA
            # in original config file

            if self._qe_dict[qe]["time"] > 0:  # Check if a sample was added to the quantum element
                # otherwise we do not add any Op

                if self._qe_dict[qe]["time"] < 16:  # Sample length must be at least 16 ns long
                    wait_duration += 16 - self._qe_dict[qe]["time"]
                    self.wait(16-self._qe_dict[qe]["time"], qe)
                if not(self._qe_dict[qe]["time"] % 4 == 0):  # Sample length must be a multiple of 4
                    wait_duration += 4 - self._qe_dict[qe]["time"] % 4
                    self.wait(4 - self._qe_dict[qe]["time"] % 4, qe)

                qe_samples = self._samples_dict[qe]
                end_samples = 0
                if "mixInputs" in elements[qe]:
                    end_samples = len(qe_samples["I"])-wait_duration
                elif "singleInput" in elements[qe]:
                    end_samples = len(qe_samples)-wait_duration
                print(qe_samples)
                print(end_samples, wait_duration)
                # Padding done according to desired method, can be either right, left, symmetric left or symmetric right

                if self._padding_method == "left":
                    if "mixInputs" in elements[qe]:
                        qe_samples["I"] = qe_samples["I"][end_samples:] + qe_samples["I"][0:end_samples]
                        qe_samples["Q"] = qe_samples["Q"][end_samples:] + qe_samples["Q"][0:end_samples]
                    elif "singleInput" in elements[qe]:
                        qe_samples = qe_samples[end_samples:] + qe_samples[0:end_samples]

                elif (self._padding_method == "symmetric_l") or (wait_duration % 2 == 0):
                    if "mixInputs" in elements[qe]:
                        qe_samples["I"] = qe_samples["I"][end_samples + wait_duration // 2:] + qe_samples["I"][0: end_samples + wait_duration // 2]
                        qe_samples["Q"] = qe_samples["Q"][end_samples + wait_duration // 2:] + qe_samples["Q"][0: end_samples + wait_duration // 2]
                    elif "singleInput" in elements[qe]:
                        qe_samples = qe_samples[end_samples + wait_duration // 2:] + qe_samples[0:end_samples + wait_duration // 2]

                elif self._padding_method == "symmetric_r":
                    if "mixInputs" in elements[qe]:
                        qe_samples["I"] = qe_samples["I"][end_samples + wait_duration // 2 + 1:] + qe_samples["I"][0:end_samples + wait_duration // 2 + 1]
                        qe_samples["Q"] = qe_samples["Q"][end_samples + wait_duration // 2 + 1:] + qe_samples["Q"][0:end_samples + wait_duration // 2 + 1]
                    elif "singleInput" in elements[qe]:
                        qe_samples = qe_samples[end_samples + wait_duration // 2 + 1:] + qe_samples[0:end_samples + wait_duration // 2 + 1]
                print(qe_samples)
                # Generates new Op, pulse, and waveform for each qe to be added in the original config file

                self._config["elements"][qe]["operations"][f"baked_Op_{self._ctr}"] = f"{qe}_baked_pulse_{self._ctr}"
                if "I" in qe_samples:
                    self._config["pulses"][f"{qe}_baked_pulse_{self._ctr}"] = {'operation': 'control',
                                                                               'length': len(qe_samples["I"]),
                                                                               'waveforms': {'I': f"{qe}_baked_wf_I_{self._ctr}",
                                                                                             'Q': f"{qe}_baked_wf_Q_{self._ctr}"}}
                    self._config["waveforms"][f"{qe}_baked_wf_I_{self._ctr}"] = \
                        {"type": "arbitrary", "samples": qe_samples["I"]}
                    self._config["waveforms"][f"{qe}_baked_wf_Q_{self._ctr}"] = \
                        {"type": "arbitrary", "samples": qe_samples["Q"]}

                elif type(qe_samples) == list:
                    self._config["pulses"][f"{qe}_baked_pulse_{self._ctr}"] = \
                        {'operation': 'control','length': len(qe_samples), 'waveforms': {'single': f"{qe}_baked_wf_{self._ctr}"}}
                    self._config["waveforms"][f"{qe}_baked_wf_{self._ctr}"] = \
                        {"type": "arbitrary", "samples": qe_samples}

    def _get_samples(self, pulse: str) -> Union[List[float], List[List]]:
        """
        Returns samples associated with a pulse
        :param pulse:
        :returns: Python list containing samples, [samples_I, samples_Q] in case of mixInputs
        """
        try:
            if 'single' in self._local_config['pulses'][pulse]['waveforms']:
                wf = self._local_config['pulses'][pulse]['waveforms']['single']
                return self._local_config['waveforms'][wf]['samples']
            elif 'I' in self._local_config['pulses'][pulse]['waveforms']:
                wf_I = self._local_config['pulses'][pulse]['waveforms']['I']
                wf_Q = self._local_config['pulses'][pulse]['waveforms']['Q']
                samples_I = self._local_config['waveforms'][wf_I]['samples']
                samples_Q = self._local_config['waveforms'][wf_Q]['samples']
                return [samples_I, samples_Q]

        except KeyError:
            raise KeyError(f'No waveforms found for pulse {pulse}')

    def _get_pulse_index(self, qe):
        index = 0
        for pulse in self._local_config["pulses"]:
            if pulse.find(f"{qe}_baked_pulse_b{self._ctr}") != -1:
                index += 1
        return index

    def add_Op(self, name: str, qe: str, samples: list, digital_marker: str = None):
        """
        Adds in the configuration file a pulse element.
        :param name: name of the Operation to be added for the quantum element
        :param qe: targeted quantum element
        :param  samples: arbitrary waveform to be inserted into pulse definition
        :param digital_marker: name of the digital marker sample associated to the generated pulse (assumed to be in the original config)
        """
        index = self._get_pulse_index(qe)
        Op = {name: f"{qe}_baked_pulse_b{self._ctr}_{index}"}
        if "mixInputs" in self._local_config["elements"][qe]:
            pulse = {
                    f"{qe}_baked_pulse_b{self._ctr}_{index}": {
                        "operation": "control",
                        "length": len(samples),
                        "waveforms": {"I": f"{qe}_baked_b{self._ctr}_{index}_wf_I",
                                      "Q": f"{qe}_baked_b{self._ctr}_{index}_wf_Q"}
                    }
                }
            if digital_marker is not None:
                pulse[f"{qe}_baked_pulse_b{self._ctr}_{index}"]["digital_marker"] = digital_marker

            waveform = {
                    f"{qe}_baked_b{self._ctr}_{index}_wf_I": {
                        'type':
                            'arbitrary',
                        'samples': samples[0]
                    },
                    f"{qe}_baked_b{self._ctr}_{index}_wf_Q": {
                        'type':
                            'arbitrary',
                        'samples': samples[1]
                    }
                }

        elif "singleInput" in self._local_config["elements"][qe]:
            pulse = {
                    f"{qe}_baked_pulse_b{self._ctr}_{index}": {
                            "operation": "control",
                            "length": len(samples),
                            "waveforms": {"single": f"{qe}_baked_b{self._ctr}_{index}_wf"}
                          }
                          }

            if digital_marker is not None:
                pulse[f"{qe}_baked_pulse_b{self._ctr}_{index}"]["digital_marker"] = digital_marker
            waveform = {

                            f"{qe}_baked_b{self._ctr}_{index}_wf": {
                                'type':
                                    'arbitrary',
                                'samples': samples
                             }
                            }

        self._local_config["pulses"].update(pulse)
        self._local_config["waveforms"].update(waveform)
        self._local_config["elements"][qe]["operations"].update(Op)

    def play(self, Op: str, qe: str, amp: float = 1.) -> None:
        """
        Add a pulse to the bake sequence
        :param Op: operation to play to quantum element
        :param qe: targeted quantum element
        :param amp: amplitude of the pulse (replaces amp(a)*'pulse' in QUA)
        :return:
        """
        try:

            if self._qe_dict[qe]["time_track"] == 0:
                pulse = self._local_config["elements"][qe]["operations"][Op]
                samples = self._get_samples(pulse)
                if "mixInputs" in self._local_config["elements"][qe]:
                    if (type(samples[0]) != list) or (type(samples[1]) != list):
                        raise TypeError(f"Error : samples given do not correspond to mixInputs for element {qe} ")
                    I = samples[0]
                    Q = samples[1]
                    I2 = [None] * len(I)
                    Q2 = [None] * len(Q)
                    phi = self._qe_dict[qe]["phase"]

                    for i in range(len(I)):
                        I2[i] = np.cos(phi)*I[i] - np.sin(phi)*Q[i]
                        Q2[i] = np.sin(phi)*I[i] + np.cos(phi)*Q[i]
                        self._samples_dict[qe]["I"].append(amp*I2[i])
                        self._samples_dict[qe]["Q"].append(amp*Q2[i])
                        self._qe_dict[qe]["phase_track"].append(phi)

                    self._update_qe_time(qe, len(I))

                elif "singleInput" in self._local_config["elements"][qe]:
                    if type(samples[0]) == list:
                        raise TypeError(f"Error : samples given do not correspond to singleInput for element {qe} ")
                    for sample in samples:
                        self._samples_dict[qe].append(amp*sample)
                    self._update_qe_time(qe, len(samples))
            else:
                self.play_at(Op, qe, self._qe_dict[qe]["time_track"], amp)
                self._qe_dict[qe]["time_track"] = 0

        except KeyError:
            raise KeyError(f'Op:"{Op}" does not exist in configuration and not manually added (use add_pulse)')

    def play_at(self, Op: str, qe: str, t: int, amp: float = 1.) -> None:
        """
        Add a waveform to the sequence at a specified time.
        If indicated time is higher than the pulse duration for the specified quantum element,
        a wait command followed by the given waveform at indicated time (in ns) occurs.
        Otherwise, waveform is added (addition of samples) to the pre-existing sequence.
        Note that the phase played for the newly formed sample is the one that was set before adding the new waveform
        :param Op: operation to play to quantum element
        :param qe: targeted quantum element
        :param t: Time tag in ns where the pulse should be added
        :param amp: amplitude of the pulse (replaces amp(a)*'pulse' in QUA)
        :return:
        """
        if type(t) != int:
            if type(t) == float:
                t = int(t)
            else:
                raise TypeError("Provided time is not an integer")
        elif t < 0:
            self.wait(t, qe)  # Negative wait
            self.play(Op, qe, amp)
        elif t > self._qe_dict[qe]["time"]:
            self.wait(t-self._qe_dict[qe]["time"], qe)
            self.play(Op, qe, amp)
        else:
            try:
                pulse = self._local_config["elements"][qe]["operations"][Op]
                samples = self._get_samples(pulse)
                new_samples = 0
                if "mixInputs" in self._local_config["elements"][qe]:
                    if (type(samples[0]) != list) or (type(samples[1]) != list):
                        raise TypeError(f"Error : samples given do not correspond to mixInputs for element {qe}"
                                        f" (Python lists must be provided for both I and Q)")
                    elif len(samples[0]) != len(samples[1]):
                        raise IndexError("Error : samples provided for I and Q do not have the same length")
                    I = samples[0]
                    Q = samples[1]
                    I2 = [None] * len(I)
                    Q2 = [None] * len(Q)
                    phi = self._qe_dict[qe]["phase_track"]

                    for i in range(len(I)):
                        if t+i < len(self._samples_dict[qe]["I"]):
                            I2[i] = np.cos(phi[t+i]) * I[i] - np.sin(phi[t+i]) * Q[i]
                            Q2[i] = np.sin(phi[t+i]) * I[i] + np.cos(phi[t+i]) * Q[i]
                            self._samples_dict[qe]["I"][t+i] += amp * I2[i]
                            self._samples_dict[qe]["Q"][t+i] += amp * Q2[i]
                        else:
                            phi = self._qe_dict[qe]["phase"]
                            I2[i] = np.cos(phi) * I[i] - np.sin(phi) * Q[i]
                            Q2[i] = np.sin(phi) * I[i] + np.cos(phi) * Q[i]
                            self._samples_dict[qe]["I"].append(amp * I2[i])
                            self._samples_dict[qe]["Q"].append(amp * Q2[i])
                            self._qe_dict[qe]["phase_track"].append(phi)
                            new_samples += 1

                elif "singleInput" in self._local_config["elements"][qe]:
                    if type(samples[0]) == list:
                        raise TypeError(f"Error : samples given do not correspond to singleInput for element {qe} ")
                    for i in range(len(samples)):
                        if t+i < len(self._samples_dict[qe]):
                            self._samples_dict[qe][t+i] += amp * samples[i]
                        else:
                            self._samples_dict[qe].append(amp * samples[i])
                            new_samples += 1

                self._update_qe_time(qe, new_samples)

            except KeyError:
                raise KeyError(f'Op:"{Op}" does not exist in configuration and not manually added (use add_pulse)')

    def frame_rotation(self, angle: float, qe: str):
        """
        Shift the phase of the oscillator associated with a quantum element by the given angle.
        This is typically used for virtual z-rotations.
        :param angle: phase parameter
        :param qe: quantum element
        """
        if "mixInputs" in self._local_config["elements"][qe]:
            self._update_qe_phase(qe, angle)
        else:
            raise TypeError(f"frame rotation not available for singleInput quantum element ({qe})")

    def frame_rotation_2pi(self, angle: float, qe: str):
        """
                Shift the phase of the oscillator associated with a quantum element by the given angle.
                This is typically used for virtual z-rotations. This performs a frame rotation of 2*π*angle
                :param angle: phase parameter
                :param qe: quantum element
                """
        if "mixInputs" in self._local_config["elements"][qe]:
            self._update_qe_phase(qe, 2*np.pi*angle)
        else:
            raise TypeError(f"frame rotation not available for singleInput quantum element ({qe})")

    def reset_frame(self, *qe_set: Set[str]):
        """
        Used to reset all of the frame updated made up to this statement.
        :param qe_set: Set[str] of quantum elements
        """
        for qe in qe_set:
            if "mixInputs" in self._local_config["elements"][qe]:
                self._update_qe_phase(qe, 0.)
            else:
                raise TypeError(f"reset frame not available for singleInput quantum element {qe}")

    def ramp(self, amp: float, duration: int, qe: str):
        """
        Analog of ramp function in QUA
        :param amp: slope
        :param duration: duration of ramping
        :param qe: quantum element
        """
        ramp_sample = [amp*t for t in range(duration)]
        if "singleInput" in self._local_config["elements"][qe]:
            self._samples_dict[qe] += ramp_sample
        elif "mixInputs" in self._local_config["elements"][qe]:
            self._samples_dict[qe]["Q"] += ramp_sample
            self._samples_dict[qe]["I"] += [0] * duration
        self._update_qe_time(qe, duration)

    def _update_qe_time(self, qe: str, dt: int):
        self._qe_dict[qe]["time"] += dt

    def _update_qe_phase(self, qe: str, phi: float):
        self._qe_dict[qe]["phase"] = phi

    def wait(self, duration: int, *qe_set: Set[str]):
        """
        Wait for the given duration on all provided elements.
        During the wait command the OPX will output 0.0 to the elements.

        :param duration: waiting duration
        :param qe_set: set of quantum elements

        """
        if duration >= 0:
            for qe in qe_set:
                if qe in self._samples_dict.keys():
                    if "mixInputs" in self._local_config["elements"][qe].keys():
                        self._samples_dict[qe]["I"] = self._samples_dict[qe]["I"] + [0] * duration
                        self._samples_dict[qe]["Q"] = self._samples_dict[qe]["Q"] + [0] * duration
                        self._qe_dict[qe]["phase_track"] += [self._qe_dict[qe]["phase"]] * duration

                    elif "singleInput" in self._local_config["elements"][qe].keys():
                        self._samples_dict[qe] = self._samples_dict[qe] + [0] * duration

                self._update_qe_time(qe, duration)
        else:
            for qe in qe_set:
                # Duration is negative so just add for substraction
                self._qe_dict[qe]["time_track"] = self._qe_dict[qe]["time"] + duration

    def align(self, *qe_set: Set[str]):
        """
        Align several quantum elements together.
        All of the quantum elements referenced in *elements will wait for all
        the others to finish their currently running statement.

        :param qe_set : set of quantum elements to be aligned altogether
        """
        last_qe = ''
        last_t = 0
        for qe in qe_set:
            qe_t = self._qe_dict[qe]["time"]

            if qe_t > last_t:
                last_qe = qe
                last_t = qe_t

        for qe in qe_set:
            qe_t = self._qe_dict[qe]["time"]
            if qe != last_qe:
                self.wait(last_t-qe_t, qe)

    def run(self) -> None:
        """
        Plays the baked waveform
        This method should be used within a QUA program
        :return None
        """
        qe_set = set()
        for qe in self._qe_dict.keys():
            # number of QEs: if >1 we need an align between all of them. if =1, no align
            if self._qe_dict[qe]["time"] > 0:
                qe_set.add(qe)

        if len(qe_set) == 1:
            for qe in qe_set:
                qua.play(f"baked_Op_{self._ctr}", qe)

        else:
            qua.align(*qe_set)
            for qe in qe_set:
                qua.play(f"baked_Op_{self._ctr}", qe)


def deterministic_run(baking_list: list):  # Not yet functioning
    depth = int(np.ceil(np.log2(len(baking_list))))
    l = 0
    h = len(baking_list)-1
    #for i in range(h + 1, 2 ** depth):
      #  baked_list.append(dummy_baked)

    def QUA_deterministic_tree(j, low: int = l, high: int = h, count: int = 1):

        mid = (high + low) // 2
        print("mid", mid)
        print("count", count)
        if high >= low:
            if count == depth:
                if mid+1 > high:
                    baking_list[mid].run()

                else:
                    with qua.if_(j > mid):
                        baking_list[mid + 1].run()
                    with qua.else_():
                        baking_list[mid].run()

            else:
                print("here")
                with qua.if_(j > mid):
                    QUA_deterministic_tree(j, mid + 1, high, count+1)
                with qua.else_():
                    QUA_deterministic_tree(j, low, mid - 1, count+1)

    return QUA_deterministic_tree

#from typing import Iterable
# def flatten(items):
#     """Yield items from any nested iterable"""
#     for x in items:
#         if isinstance(x, Iterable) and not isinstance(x, (str, bytes)):
#             yield from flatten(x)
#         else:
#             yield x
