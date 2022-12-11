import numpy as np

from sequence_jacobian.blocks.stage_block import StageBlock
from sequence_jacobian.hetblocks.hh_sim import hh, hh_init
from sequence_jacobian.blocks.support.stages import Continuous1D, ExogenousMaker
from sequence_jacobian import interpolate, grids, misc, combine
from sequence_jacobian.classes import ImpulseDict

def make_grids(rho_e, sd_e, nE, amin, amax, nA):
    e_grid, e_dist, Pi_ss = grids.markov_rouwenhorst(rho=rho_e, sigma=sd_e, N=nE)
    a_grid = grids.agrid(amin=amin, amax=amax, n=nA)
    return e_grid, e_dist, Pi_ss, a_grid

def alter_Pi(Pi_ss, shift):
    Pi = Pi_ss.copy()
    Pi[:, 0] -= shift
    Pi[:, -1] += shift
    return Pi

def income(atw, N, e_grid, transfer):
    y = atw * N * e_grid + transfer
    return y

# copy original household hetblock but get rid of _p on Va
def household_new(Va, a_grid, y, r, beta, eis):
    uc_nextgrid = beta * Va
    c_nextgrid = uc_nextgrid ** (-eis)
    coh = (1 + r) * a_grid[np.newaxis, :] + y[:, np.newaxis]
    a = interpolate.interpolate_y(c_nextgrid + a_grid, coh, a_grid)
    misc.setmin(a, a_grid[0])
    c = coh - a
    Va = (1 + r) * c ** (-1 / eis)
    return Va, a, c

def marginal_utility(c, eis):
    uc = c ** (-1 / eis)
    return uc

#het_stage = Continuous1D(backward='Va', policy='a', f=household_new, name='stage1')
het_stage = Continuous1D(backward='Va', policy='a', f=household_new, name='stage1', hetoutputs=[marginal_utility])
hh2 = StageBlock([ExogenousMaker('Pi', 0, 'stage0'), het_stage], name='hh',
                    backward_init=hh_init, hetinputs=(make_grids, income, alter_Pi))

def test_equivalence():
    hh1 = hh.add_hetinputs([make_grids, income, alter_Pi]).add_hetoutputs([marginal_utility])
    calibration = {'r': 0.004, 'eis': 0.5, 'rho_e': 0.91, 'sd_e': 0.92, 'nE': 3,
                   'amin': 0.0, 'amax': 200, 'nA': 100, 'transfer': 0.143, 'N': 1,
                   'atw': 1, 'beta': 0.97, 'shift': 0}
    ss1 = hh1.steady_state(calibration)
    ss2 = hh2.steady_state(calibration)

    # test steady-state equivalence
    assert np.isclose(ss1['A'], ss2['A'])
    assert np.isclose(ss1['C'], ss2['C'])
    assert np.allclose(ss1.internals['hh']['Dbeg'], ss2.internals['hh']['stage0']['D'])
    assert np.allclose(ss1.internals['hh']['a'], ss2.internals['hh']['stage1']['a'])
    assert np.allclose(ss1.internals['hh']['c'], ss2.internals['hh']['stage1']['c'])
    assert np.allclose(ss1.internals['hh']['Va'], ss2.internals['hh']['stage0']['Va'])

    # find Jacobians...
    inputs = ['r', 'atw', 'shift']
    outputs = ['A', 'C', 'UC']
    T = 200
    J1 = hh1.jacobian(ss1, inputs, outputs, T)
    J2 = hh2.jacobian(ss2, inputs, outputs, T)

    # test Jacobian equivalence
    for i in inputs:
        for o in outputs:
            if o == 'UC':
                # not sure why numerical differences somewhat larger here?
                assert np.max(np.abs(J1[o, i] - J2[o, i])) < 2E-4
            else:
                assert np.allclose(J1[o, i], J2[o, i])

    # impulse linear
    shock = ImpulseDict({'r': 0.5 ** np.arange(20)})
    td_lin1 = hh1.impulse_linear(ss1, shock, outputs=['C', 'UC'])
    td_lin2 = hh2.impulse_linear(ss2, shock, outputs=['C', 'UC'])
    assert np.allclose(td_lin1['C'], td_lin2['C'])
    assert np.max(np.abs(td_lin1['UC'] - td_lin2['UC'])) < 2E-4

    # impulse nonlinear
    td_nonlin1 = hh1.impulse_nonlinear(ss1, shock * 1E-4, outputs=['C', 'UC'])
    td_nonlin2 = hh2.impulse_nonlinear(ss2, shock * 1E-4, outputs=['C', 'UC'])
    assert np.allclose(td_nonlin1['C'], td_nonlin2['C'])
    assert np.allclose(td_nonlin1['UC'], td_nonlin2['UC'])


def test_remap():
    # hetblock
    hh1 = hh.add_hetinputs([make_grids, income, alter_Pi])
    hh1_men = hh1.remap({k: k + '_men' for k in hh1.outputs | ['sd_e']}).rename('men')
    hh1_women = hh1.remap({k: k + '_women' for k in hh1.outputs | ['sd_e']}).rename('women')
    hh1_all = combine([hh1_men, hh1_women])

    # stageblock
    hh2_men = hh2.remap({k: k + '_men' for k in hh2.outputs| ['sd_e']}).rename('men')
    hh2_women = hh2.remap({k: k + '_women' for k in hh2.outputs | ['sd_e']}).rename('women')
    hh2_all = combine([hh2_men, hh2_women])

    # steady state
    calibration = {'sd_e_men': 0.92, 'sd_e_women': 0.82, 
                   'r': 0.004, 'eis': 0.5, 'rho_e': 0.91, 'nE': 3,
                   'amin': 0.0, 'amax': 200, 'nA': 100, 'transfer': 0.143, 'N': 1,
                   'atw': 1, 'beta': 0.97, 'shift': 0}

    ss1 = hh1_all.steady_state(calibration)
    ss2 = hh2_all.steady_state(calibration)

    # test steady-state equivalence
    assert np.isclose(ss1['A_men'], ss2['A_men'])
    assert np.isclose(ss1['C_women'], ss2['C_women'])

    # find Jacobians...
    inputs = ['r', 'atw', 'shift']
    outputs = ['A_men', 'A_women']
    T = 100
    J1 = hh1_all.jacobian(ss1, inputs, outputs, T)
    J2 = hh2_all.jacobian(ss2, inputs, outputs, T)

    # test Jacobian equivalence
    for i in inputs:
        for o in outputs:
            assert np.allclose(J1[o, i], J2[o, i])

    # impulse linear
    shock = ImpulseDict({'r': 0.5 ** np.arange(20)})
    td_lin1 = hh1_all.impulse_linear(ss1, shock, outputs=['C_men', 'C_women'])
    td_lin2 = hh2_all.impulse_linear(ss2, shock, outputs=['C_men', 'C_women'])
    assert np.allclose(td_lin1['C_women'], td_lin2['C_women'])

    # impulse nonlinear
    td_nonlin1 = hh1_all.impulse_nonlinear(ss1, shock * 1E-4, outputs=['C_men'])
    td_nonlin2 = hh2_all.impulse_nonlinear(ss2, shock * 1E-4, outputs=['C_men'])
    assert np.allclose(td_nonlin1['C_men'], td_nonlin2['C_men'])
