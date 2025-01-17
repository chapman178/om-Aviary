from pathlib import Path
from openmdao.utils.reports_system import register_report

import numpy as np

from aviary.interface.utils.markdown_utils import write_markdown_variable_table
from aviary.utils.named_values import NamedValues


def register_custom_reports():
    """
    Registers Aviary reports with openMDAO, so they are automatically generated and
    added to the same reports folder as other default reports
    """
    # TODO top-level aircraft report?
    # TODO add flag to skip registering reports?

    # register per-subsystem report generation
    register_report(name='subsystems',
                    func=subsystem_report,
                    desc='Generates reports for each subsystem builder in the '
                         'Aviary Problem',
                    class_name='AviaryProblem',
                    method='run_driver',
                    pre_or_post='post',
                    # **kwargs
                    )

    register_report(name='mission',
                    func=mission_report,
                    desc='Generates report for mission results from Aviary problem',
                    class_name='AviaryProblem',
                    method='run_driver',
                    pre_or_post='post')


def subsystem_report(prob, **kwargs):
    """
    Loops through all subsystem builders in the AviaryProblem calls their write_report
    method. All generated report files are placed in the "reports/subsystem_reports" folder

    Parameters
    ----------
    prob : AviaryProblem
        The AviaryProblem used to generate this report
    """
    reports_folder = Path(prob.get_reports_dir() / 'subsystems')
    reports_folder.mkdir(exist_ok=True)

    # TODO external subsystems??
    core_subsystems = prob.core_subsystems

    for subsystem in core_subsystems.values():
        subsystem.report(prob, reports_folder, **kwargs)


def mission_report(prob, **kwargs):
    """
    Creates a basic mission summary report that is place in the "reports" folder

    Parameters
    ----------
    prob : AviaryProblem
        The AviaryProblem used to generate this report
    """
    def _get_phase_value(traj, phase, var_name, units, indices=None):
        try:
            vals = prob.get_val(f"{traj}.{phase}.timeseries.{var_name}",
                                units=units,
                                indices=indices,)
        except KeyError:
            try:
                vals = prob.get_val(f"{traj}.{phase}.{var_name}",
                                    units=units,
                                    indices=indices,)
            # 2DOF breguet range cruise uses time integration to track mass
            except TypeError:
                vals = prob.get_val(f"{traj}.{phase}.timeseries.time",
                                    units=units,
                                    indices=indices,)
            except KeyError:
                vals = None

        return vals

    def _get_phase_diff(traj, phase, var_name, units, indices=[0, -1]):
        vals = _get_phase_value(traj, phase, var_name, units, indices)

        if vals is not None:
            diff = vals[-1]-vals[0]
            if isinstance(diff, np.ndarray):
                diff = diff[0]
            return diff
        else:
            return None

    reports_folder = Path(prob.get_reports_dir())
    report_file = reports_folder / 'mission_summary.md'

    # read per-phase data from trajectory
    data = {}
    for idx, phase in enumerate(prob.phase_info):
        # TODO for traj in trajectories, currently assuming single one named "traj"
        # TODO delta mass and fuel consumption need to be tracked separately
        fuel_burn = _get_phase_diff('traj', phase, 'mass', 'lbm', [-1, 0])
        time = _get_phase_diff('traj', phase, 't', 'min')
        range = _get_phase_diff('traj', phase, 'distance', 'nmi')

        # get initial values, first in traj
        if idx == 0:
            initial_mass = _get_phase_value('traj', phase, 'mass', 'lbm', 0)[0]
            initial_time = _get_phase_value('traj', phase, 't', 'min', 0)
            initial_range = _get_phase_value('traj', phase, 'distance', 'nmi', 0)[0]

        outputs = NamedValues()
        # Fuel burn is negative of delta mass
        outputs.set_val('Fuel Burn', fuel_burn, 'lbm')
        outputs.set_val('Elapsed Time', time, 'min')
        outputs.set_val('Ground Distance', range, 'nmi')
        data[phase] = outputs

        # get final values, last in traj
        final_mass = _get_phase_value('traj', phase, 'mass', 'lbm', -1)[0]
        final_time = _get_phase_value('traj', phase, 't', 'min', -1)
        final_range = _get_phase_value('traj', phase, 'distance', 'nmi', -1)[0]

    totals = NamedValues()
    totals.set_val('Total Fuel Burn', initial_mass - final_mass, 'lbm')
    totals.set_val('Total Time', final_time - initial_time, 'min')
    totals.set_val('Total Ground Distance', final_range - initial_range, 'nmi')

    with open(report_file, mode='w') as f:
        f.write('# MISSION SUMMARY')
        write_markdown_variable_table(f, totals,
                                      ['Total Fuel Burn',
                                       'Total Time',
                                       'Total Ground Distance'],
                                      {'Total Fuel Burn': {'units': 'lbm'},
                                       'Total Time': {'units': 'min'},
                                       'Total Ground Distance': {'units': 'nmi'}})

        f.write('\n# MISSION SEGMENTS')
        for phase in data:
            f.write(f'\n## {phase}')
            write_markdown_variable_table(f, data[phase], ['Fuel Burn', 'Elapsed Time', 'Ground Distance'],
                                          {'Fuel Burn': {'units': 'lbm'},
                                           'Elapsed Time': {'units': 'min'},
                                           'Ground Distance': {'units': 'nmi'}})
