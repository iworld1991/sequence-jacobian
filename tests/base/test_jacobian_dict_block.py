"""Test JacobianDictBlock functionality"""

import numpy as np

from sequence_jacobian import combine
from sequence_jacobian.examples import rbc
from sequence_jacobian.blocks.auxiliary_blocks.jacobiandict_block import JacobianDictBlock
from sequence_jacobian import SteadyStateDict


def test_jacobian_dict_block_impulses(rbc_dag):
    rbc_model, ss, unknowns, _, exogenous = rbc_dag

    T = 10
    J_pe = rbc_model.jacobian(ss, inputs=unknowns + exogenous, T=10)
    J_block = JacobianDictBlock(J_pe)

    J_block_Z = J_block.jacobian(SteadyStateDict({}), ["Z"])
    for o in J_block_Z.outputs:
        assert np.all(J_block[o].get("Z") == J_block_Z[o].get("Z"))

    dZ = 0.8 ** np.arange(T)

    dO1 = J_block @ {"Z": dZ}
    dO2 = J_block_Z @ {"Z": dZ}

    for k in J_block:
        assert np.all(dO1[k] == dO2[k])


def test_jacobian_dict_block_combine(rbc_dag):
    _, ss, _, _, exogenous = rbc_dag

    J_firm = rbc.firm.jacobian(ss, inputs=exogenous)
    blocks_w_jdict = [rbc.household, J_firm, rbc.mkt_clearing]
    cblock_w_jdict = combine(blocks_w_jdict)

    # Using `combine` converts JacobianDicts to JacobianDictBlocks
    assert isinstance(cblock_w_jdict.blocks[0], JacobianDictBlock)
