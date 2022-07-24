import numpy as np
import pytest
from spgrep.group import get_little_group
from spgrep.irreps import enumerate_small_representations
from spgrep.representation import check_spacegroup_representation, is_unitary

from phonopy.structure.symmetry import Symmetry
from spgrep_modulation.irreps import (
    get_eigenmode_representation,
    project_eigenmode_representation,
)


@pytest.mark.parametrize(
    "ph_name,qpoint,num_irreps,num_basis",
    [
        ("ph_si_diamond", [0, 0, 0], 2, [1, 1]),
        ("ph_si_diamond", [0.5, 0, 0.5], 3, [1, 1, 1]),  # X point in primitive
        ("ph_si_diamond", [0.25, 0.25, 0.5], 4, [2, 1, 1, 2]),  # Sigma line in primitive
        ("ph_mgo", [0, 0, 0], 1, [2]),
        ("ph_mgo", [0.5, 0, 0.5], 2, [2, 2]),  # X point in primitive
        ("ph_bto", [0.0, 0.0, 0.0], 2, [4, 1]),  # Gamma point
        ("ph_bto", [0.0, 0.5, 0.5], 8, [1, 1, 1, 1, 3, 1, 2, 1]),  # TODO: M point
    ],
)
def test_project_eigenmode_representation(request, ph_name, qpoint, num_irreps, num_basis):
    ph = request.getfixturevalue(ph_name)

    primitive = ph.dynamical_matrix.primitive
    primitive_symmetry = Symmetry(cell=primitive)

    rep = get_eigenmode_representation(primitive, primitive_symmetry, qpoint)
    all_basis, irreps, mapping = project_eigenmode_representation(
        rep, primitive, primitive_symmetry, qpoint
    )
    assert len(irreps) == num_irreps
    assert [len(b) for b in all_basis] == num_basis
    assert sum(sum(len(bb) for bb in b) for b in all_basis) == len(primitive) * 3

    # Check irreps
    num_atoms = len(primitive)
    phase = np.exp(2j * np.pi * np.dot(primitive.scaled_positions, qpoint))  # (num_atoms, )
    for list_basis, irrep in zip(all_basis, irreps):
        for basis in list_basis:
            modified_basis = basis * phase[None, :, None]
            F = modified_basis.reshape(-1, num_atoms * 3).T  # (num_atoms * 3, dim_irrep)
            actuals = np.einsum(
                "ip,kij,jq->kpq",
                np.conj(F),
                rep[mapping].reshape(-1, num_atoms * 3, num_atoms * 3),
                F,
                optimize="greedy",
            )
            assert np.allclose(actuals, irrep)

    # Check if modified dynamical matrix is invariant under eigenmode representation
    dm = ph.dynamical_matrix
    dm.run(qpoint)
    mdm = (
        dm.dynamical_matrix.reshape(num_atoms, 3, num_atoms, 3)
        * phase[:, None, None, None]
        * np.conj(phase)[None, None, :, None]
    )
    mdm = mdm.reshape(num_atoms * 3, num_atoms * 3)
    for idx in mapping:
        rep_idx = rep[idx].reshape(num_atoms * 3, num_atoms * 3)
        actual = rep_idx @ mdm @ np.conj(rep_idx.T)
        assert np.allclose(actual, mdm, atol=1e-5)


def test_symmetry_adapted_basis(ph_bto):
    # Perovskite structure at Gamma point
    # Ref: https://stokes.byu.edu/iso/isotheory.pdf
    ph = ph_bto
    qpoint = [0, 0, 0]

    primitive = ph.dynamical_matrix.primitive  # symbols = ['O', 'O', 'O', 'Ti', 'Ba']
    primitive_symmetry = Symmetry(cell=primitive)

    rep = get_eigenmode_representation(primitive, primitive_symmetry, qpoint)
    basis, irreps, mapping = project_eigenmode_representation(
        rep, primitive, primitive_symmetry, qpoint
    )
    assert len(irreps) == 2
    assert [len(b) for b in basis] == [4, 1]

    s = 1 / np.sqrt(2)

    # Acoustic (O)
    gamma_4m_0 = np.zeros((3, 5, 3), dtype=np.complex_)
    gamma_4m_0[0, 2, 2] = gamma_4m_0[1, 0, 0] = gamma_4m_0[2, 1, 1] = 1
    assert np.allclose(basis[0][0], gamma_4m_0)

    # Acoustic (O)
    gamma_4m_1 = np.zeros((3, 5, 3), dtype=np.complex_)
    gamma_4m_1[0, 0, 2] = gamma_4m_1[0, 1, 2] = s
    gamma_4m_1[1, 1, 0] = gamma_4m_1[1, 2, 0] = s
    gamma_4m_1[2, 0, 1] = gamma_4m_1[2, 2, 1] = s
    assert np.allclose(basis[0][1], gamma_4m_1)

    # Acoustic (Ti)
    gamma_4m_2 = np.zeros((3, 5, 3), dtype=np.complex_)
    gamma_4m_2[0, 3, 2] = gamma_4m_2[1, 3, 0] = gamma_4m_2[2, 3, 1] = 1
    assert np.allclose(basis[0][2], gamma_4m_2)

    # Acoustic (Ba)
    gamma_4m_3 = np.zeros((3, 5, 3), dtype=np.complex_)
    gamma_4m_3[0, 4, 2] = gamma_4m_3[1, 4, 0] = gamma_4m_3[2, 4, 1] = 1
    assert np.allclose(basis[0][3], gamma_4m_3)

    # Optic (O)
    gamma_5m = np.zeros((3, 5, 3), dtype=np.complex_)
    gamma_5m[0, 0, 2] = -s
    gamma_5m[0, 1, 2] = s
    gamma_5m[1, 1, 0] = -s
    gamma_5m[1, 2, 0] = s
    gamma_5m[2, 0, 1] = s
    gamma_5m[2, 2, 1] = -s
    assert np.allclose(basis[1][0], gamma_5m)


@pytest.mark.parametrize(
    "ph_name,qpoint",
    [
        ("ph_mgo", [0.0, 0.0, 0.0]),  # Gamma point
        ("ph_mgo", [0.0, 0.5, 0.5]),  # M point
        ("ph_bto", [0.0, 0.0, 0.0]),  # Gamma point
        ("ph_bto", [0.0, 0.5, 0.5]),  # M point
        ("ph_si_diamond", [0, 0, 0]),
        ("ph_si_diamond", [0.5, 0, 0.5]),  # X point in primitive
    ],
)
def test_eigenmode_representation(request, ph_name, qpoint):
    ph = request.getfixturevalue(ph_name)

    primitive = ph.dynamical_matrix.primitive
    primitive_symmetry = Symmetry(cell=primitive)

    rep = get_eigenmode_representation(primitive, primitive_symmetry, qpoint)

    little_rotations, little_translations, mapping = get_little_group(
        primitive_symmetry.symmetry_operations["rotations"],
        primitive_symmetry.symmetry_operations["translations"],
        qpoint,
    )

    num_atoms = len(primitive)
    # Check if `rep` is unitary representation
    assert is_unitary(rep.reshape(-1, num_atoms * 3, num_atoms * 3))
    # Check if `rep` preserves multiplication for little group
    assert check_spacegroup_representation(
        little_rotations,
        little_translations,
        qpoint,
        rep[mapping].reshape(-1, num_atoms * 3, num_atoms * 3),
    )

    irreps = enumerate_small_representations(little_rotations, little_translations, qpoint)
    for irrep in irreps:
        assert check_spacegroup_representation(
            little_rotations,
            little_translations,
            qpoint,
            irrep,
        )
