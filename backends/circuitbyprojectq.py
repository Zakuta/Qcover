import os
from collections import defaultdict
from multiprocessing import cpu_count
import networkx as nx
import matplotlib.pyplot as plt
import numpy as np
from multiprocessing import Pool
from projectq.cengines import BasicEngine
from projectq.backends import ResourceCounter
from projectq import MainEngine
from projectq.ops import QubitOperator, All, H, Rx, Measure, MatrixGate, Rz, Rzz, Z
from projectq.setups import linear


class CircuitByProjectq:
    """generate a instance of CircuitByProjectq"""
    def __init__(self,
                 # p: int = 1,
                 nodes_weight: list = None,
                 edges_weight: list = None,
                 is_parallel: bool = None) -> None:
        """initialize a instance of CircuitByProjectq"""

        self._p = None
        self._nodes_weight = nodes_weight
        self._edges_weight = edges_weight
        self._is_parallel = False if is_parallel is None else is_parallel

        self._element_to_graph = None
        self._pargs = None
        self._expectation_path = []

    @staticmethod
    def get_operator(element):
        op = QubitOperator()
        if isinstance(element, int):
            op += QubitOperator('Z' + str(element))
        else:
            op += QubitOperator('Z' + str(element[0])) + QubitOperator('Z' + str(element[1]))
        return op

    def get_expectation(self, element_graph):
        """
        transform the graph to circuit according to the computing_framework
        Args:
            graph (nx.Graph): graph to be transformed to circuit
            params (np.array): Optimal parameters
            original_e (Optional[None, int, tuple])
        Return:
            if original_e=None, then the graph is the whole original graph generated by
            generate_weighted_graph(), so just return the circuit transformed by it

            if original_e is a int, then the subgraph is generated by node(idx = original_e
            in whole graph), so return the it's idx mapped by node_to_qubit[], and the circuit

            if original_e is a tuple, then the subgraph is generated by edge(node idx = original_e
            in whole graph), so return the it's idx mapped by node_to_qubit[] as
            tuple(mapped node_id1, mapped node_id2), and the circuit
        """
        original_e, graph = element_graph
        node_to_qubit = defaultdict(int)
        node_list = list(graph.nodes)
        for i in range(len(node_list)):
            node_to_qubit[node_list[i]] = i

        gamma_list, beta_list = self._pargs[: self._p], self._pargs[self._p:]
        eng = MainEngine()
        qubits = eng.allocate_qureg(len(graph.nodes))
        All(H) | qubits

        for k in range(self._p):
            for edge in graph.edges:
                u, v = node_to_qubit[edge[0]], node_to_qubit[edge[1]]
                if u == v:
                    continue
                Rzz(2 * gamma_list * self._edges_weight[edge[0], edge[1]]) | (qubits[u], qubits[v])

            for nd in graph.nodes:
                u = node_to_qubit[nd]
                Rz(2 * gamma_list * self._nodes_weight[nd]) | qubits[u]
                Rx(2 * beta_list) | qubits[u]

        # print("before flush")
        eng.flush()
        # print("after flush")
        # print("the original element is", original_e)
        # assert len(qubits) == len(node_list)
        if isinstance(original_e, int):
            weight = self._nodes_weight[original_e]
            op = self.get_operator(node_to_qubit[original_e])
        else:
            weight = self._edges_weight[original_e]
            op = self.get_operator((node_to_qubit[original_e[0]], node_to_qubit[original_e[1]]))

        exp_res = eng.backend.get_expectation_value(op, qubits)
        All(Measure) | qubits
        eng.flush(deallocate_qubits=True)        #

        return weight * exp_res

    def expectation_calculation(self):
        if self._is_parallel:
            return self.expectation_calculation_parallel()
        else:
            return self.expectation_calculation_serial()

    def expectation_calculation_serial(self):
        cpu_num = cpu_count()  # 自动获取最大核心数目
        os.environ['OMP_NUM_THREADS'] = str(cpu_num)
        os.environ['OPENBLAS_NUM_THREADS'] = str(cpu_num)
        os.environ['MKL_NUM_THREADS'] = str(cpu_num)
        os.environ['VECLIB_MAXIMUM_THREADS'] = str(cpu_num)
        os.environ['NUMEXPR_NUM_THREADS'] = str(cpu_num)

        res = 0
        for item in self._element_to_graph.items():
            res += self.get_expectation(item)

        print("Total expectation of original graph is: ", res)
        self._expectation_path.append(res)
        return res

    def expectation_calculation_parallel(self):
        cpu_num = 1
        os.environ['OMP_NUM_THREADS'] = str(cpu_num)
        os.environ['OPENBLAS_NUM_THREADS'] = str(cpu_num)
        os.environ['MKL_NUM_THREADS'] = str(cpu_num)
        os.environ['VECLIB_MAXIMUM_THREADS'] = str(cpu_num)
        os.environ['NUMEXPR_NUM_THREADS'] = str(cpu_num)

        circ_res = []
        pool = Pool(os.cpu_count())
        circ_res.append(pool.map(self.get_expectation, list(self._element_to_graph.items()), chunksize=1))

        pool.terminate()  # pool.close()
        pool.join()

        res = sum(circ_res[0])
        print("Total expectation of original graph is: ", res)
        self._expectation_path.append(res)
        return res

    def visualization(self):
        plt.figure()
        plt.plot(range(1, len(self._expectation_path) + 1), self._expectation_path, "ob-", label="projectq")
        plt.ylabel('Expectation value')
        plt.xlabel('Number of iterations')
        plt.legend()
        plt.show()
