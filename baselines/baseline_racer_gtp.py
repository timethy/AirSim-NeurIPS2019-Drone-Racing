import gtp
from baseline_racer import BaselineRacer
from utils import to_airsim_vector, to_airsim_vectors
from visualize import *
from matplotlib import pyplot as plt

import airsimneurips as airsim
import time
import numpy as np

import argparse


class BaselineRacerGTP(BaselineRacer):
    def __init__(self, traj_params, drone_names, drone_i, drone_params):
        super().__init__()
        self.drone_names = drone_names
        self.drone_i = drone_i
        self.drone_params = drone_params
        self.traj_params = traj_params

        self.controller = None

        # For plotting: Just some fig, ax and line objects to keep track of
        self.fig, self.ax = plt.subplots()
        self.line_state = None
        self.lines = [None] * 2

    def update_and_plan(self):
        # Retrieve the current state from AirSim
        position_airsim = []
        vels_airsim = []
        for drone_name in self.drone_names:
            mr_state = self.airsim_client.getMultirotorState(vehicle_name=drone_name)
            position_airsim.append(mr_state.kinematics_estimated.position)
            vels_airsim.append(mr_state.kinematics_estimated.linear_velocity)

        state = np.array([position.to_numpy_array() for position in position_airsim])

        # Plot or update the state
        if self.line_state is None:
            self.line_state, = plot_state(self.ax, state)
        else:
            replot_state(self.line_state, state)

        i = self.drone_i
        trajectory = self.controller.callback(i, state, [])

        # Now, let's issue the new trajectory to the trajectory planner
        # Fetch the current state first, to see, if our trajectory is still planned for ahead of us
        mr_state = self.airsim_client.getMultirotorState(vehicle_name=self.drone_name)
        new_state_i = mr_state.kinematics_estimated.position.to_numpy_array()

        state[i, :] = new_state_i
        replot_state(self.line_state, state)

        # As we move while computing the trajectory,
        # make sure that we only issue the part of the trajectory, that is still ahead of us
        k_truncate, t = self.controller.truncate(i, new_state_i, trajectory[:, :])

        print(k_truncate)

        # k_truncate == args.n means that the whole trajectory is behind us, and we only issue the last point
        if k_truncate == self.traj_params.n:
            k_truncate = self.traj_params.n - 1

        # Let's plot or update the 2D trajectory
        if self.lines[i] is None:
            self.lines[i], = plot_trajectory_2d(self.ax, trajectory[k_truncate:, :])
        else:
            replot_trajectory_2d(self.lines[i], trajectory[k_truncate:, :])

        # Finally issue the command to AirSim.
        # This returns a future, that we do not call .join() on, as we want to re-issue a new command
        # once we compute the next iteration of our high-level planner
        self.airsim_client.moveOnSplineAsync(to_airsim_vectors(trajectory[k_truncate:k_truncate + 4, :]),
                                             add_curr_odom_position_constraint=True,
                                             add_curr_odom_velocity_constraint=True,
                                             vel_max=15.0, acc_max=10.0, vehicle_name=self.drone_name)
        time.sleep(1.0)

        vels = (trajectory[1:, :] - trajectory[:-1, :]) / self.traj_params.dt

        # print(np.linalg.norm(vels, axis=1))
        # print(to_airsim_vectors(vels[0:, :]))
        # Note: Need at least 2 vertices if position_constraint is off
        # client.moveOnSplineVelConstraintsAsync(
        #     to_airsim_vectors(trajectories[i, k_truncate:, :]),
        #     to_airsim_vectors(vels[k_truncate:, :]),
        #     vel_max=8.0, acc_max=10.0,
        #     add_curr_odom_position_constraint=True,
        #     add_curr_odom_velocity_constraint=False,
        #     vehicle_name=drone_name)

        # Refresh the updated plot
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()

    def run(self):
        gate_poses = self.get_ground_truth_gate_poses()

        # We pretend we have two different controllers for the drones,
        # so let's instantiate two
        self.controller = gtp.Controller(self.traj_params, self.drone_params, gate_poses)

        # Let's plot the gates, and the fitted track.
        plot_gates_2d(self.ax, gate_poses)
        plot_track(self.ax, self.controller.track)
        plot_track_arrows(self.ax, self.controller.track)
        plt.show()

        # Always a good idea to sleep a little
        time.sleep(1.0)

        while self.airsim_client.isApiControlEnabled(vehicle_name=self.drone_name):
            self.update_and_plan()


def main(args):
    drone_names = ["drone_0", "drone_1"]

    drone_params = [
        {"r_safe": 0.4,
         "r_coll": 0.3,
         "v_max": 15.0},
        {"r_safe": 0.4,
         "r_coll": 0.3,
         "v_max": 15.0}]

    # ensure you have generated the neurips planning settings file by running python generate_settings_file.py
    baseline_racer = BaselineRacerGTP(
        traj_params=args,  # TODO: For dt and n
        drone_names=drone_names,
        drone_i=0,
        drone_params=drone_params)

    baseline_racer.load_level(args.level)
    baseline_racer.initialize_drone()
    baseline_racer.takeoff_with_moveOnSpline()
    baseline_racer.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--dt', type=float, default=0.5)
    parser.add_argument('--n', type=int, default=8)
    parser.add_argument('level')
    main(parser.parse_args())