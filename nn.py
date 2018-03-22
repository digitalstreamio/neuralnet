#%%
import h5py
import matplotlib.pyplot as plt
import numpy as np
import time
from collections import namedtuple


def relu(z):
    return np.maximum(0, z)


def relu_backward(dA, Z):
    return np.multiply(dA, np.int64(Z > 0))


def relu_derv(z):
    return np.where(z >= 0, 1.0, 0.0)


def sigmoid(z):
    return 1. / (1. + np.exp(-z))


def sigmoid_backward(dA, z):
    a = sigmoid(z)
    return dA * a * (1 - a)


def sigmoid_derv(z):
    a = sigmoid(z)
    return a * (1 - a)


class GradDescentOptimizer:
    def __init__(self, iters, alpha, debug=False):
        self.alpha = alpha
        self.debug = debug
        self.iters = iters

    def optimize(self, cost_fn, params):
        costs = []
        for i in range(self.iters):
            cost, grad = cost_fn(params)
            params = params - self.alpha * grad
            if i % 100 == 0:
                costs.append(cost)
                if self.debug:
                    print('cost[{}]: {}'.format(i, cost))
        return params, costs


NnLayer = namedtuple('NnLayer', ['dim', 'activation'])


class NnModel:
    def __init__(self):
        self.layers = []
        # Compiled
        self.layer_offsets = []
        self.activations = {
            'relu': (relu, relu_derv, relu_backward),
            'sigmoid': (sigmoid, sigmoid_derv, sigmoid_backward)
        }

    def __getitem__(self, key):
        return self.layers[key]

    def __len__(self):
        return len(self.layers)

    def add(self, units, activation, input_dim=0):
        if input_dim != 0 and not self.layers:
            self.layers.append(NnLayer(input_dim, None))
        self.layers.append(NnLayer(units, self.activations[activation]))

    def compile(self):
        offset = 0
        self.layer_offsets = [(0, 0)]
        for layer in range(1, len(self.layers)):
            prev_layer_dim = self.layers[layer - 1].dim
            layer_dim = self.layers[layer].dim
            w_offset = (offset, offset + prev_layer_dim * layer_dim)
            b_offset = (w_offset[1], w_offset[1] + layer_dim)
            self.layer_offsets.append((w_offset, b_offset))
            offset += prev_layer_dim * layer_dim + layer_dim

    def pack_params(self, layer, params, W, b):
        assert (W.shape == (self.layers[layer].dim,
                            self.layers[layer - 1].dim))
        assert (b.shape == (self.layers[layer].dim, 1))
        w_offset, b_offset = self.layer_offsets[layer]
        params = params.reshape((-1, 1))
        params[w_offset[0]:w_offset[1], ...] = W.reshape((-1, 1))
        params[b_offset[0]:b_offset[1], ...] = b.reshape((-1, 1))

    def unpack_params(self, layer, params):
        prev_layer_dim = self.layers[layer - 1].dim
        layer_dim = self.layers[layer].dim
        w_offset, b_offset = self.layer_offsets[layer]
        W = params[w_offset[0]:w_offset[1], ...].reshape((layer_dim,
                                                          prev_layer_dim))
        b = params[b_offset[0]:b_offset[1], ...].reshape((layer_dim, 1))
        return W, b


class NnClassifier:
    def __init__(self, model, optimizer, lambd):
        self.model = model
        self.optimizer = optimizer
        self.params = None
        self.lambd = lambd

    def predict(self, X):
        assert X.shape[0] == self.model[0].dim
        A = X
        for l in range(1, len(self.model)):
            layer = self.model[l]
            W, b = self.model.unpack_params(l, self.params)
            Z = np.dot(W, A) + b
            A = layer.activation[0](Z)
            assert A.shape == (layer.dim, X.shape[1])
        Y_pred = A > 0.5
        assert Y_pred.shape == (1, X.shape[1])
        return Y_pred

    def train(self, X, Y):
        def J(params):
            return self._cost(params, X, Y)

        guess = self._init_params()
        self.params, costs = self.optimizer.optimize(J, guess)
        return costs

    def _init_params(self, epsilon=0.01):
        np.random.seed(5)
        dim = 0
        for l in range(1, len(self.model)):
            dim += self.model[l].dim * self.model[l - 1].dim
            dim += self.model[l].dim
        params = np.zeros(dim, dtype=np.float)
        for l in range(1, len(self.model)):
            prev_layer_dim = self.model[l - 1].dim
            layer_dim = self.model[l].dim
            W = np.random.randn(layer_dim, prev_layer_dim) * np.sqrt(
                2. / prev_layer_dim)  #/ np.sqrt(prev_layer_dim)
            b = np.zeros((layer_dim, 1), dtype=np.float)
            self.model.pack_params(l, params, W, b)
        return params

    def _cost(self, params, X, Y):
        A, Z = self._propagate_forward(params, X)
        cost = self._compute_cost(params, A[-1], Y)
        grad = self._propagate_backward(params, A, Z, Y)
        return cost, grad

    def _compute_cost(self, params, AL, Y):
        m = AL.shape[1]
        # loss (1 x m)
        L = -(Y * np.log(AL) + (1 - Y) * np.log(1. - AL))
        # cross-entropy cost (scalar)
        J = (1. / m) * np.sum(L)
        for l in range(1, len(self.model)):
            # weights (n[l] x n[l-1]), bias (n[l] x 1)
            W, b = self.model.unpack_params(l, params)
            # regularized cost
            J += (self.lambd / (2 * m)) * np.sum(np.square(W))
        return J

    def _propagate_forward(self, params, X):
        A = [X]
        Z = [None]
        for l in range(1, len(self.model)):
            layer = self.model[l]
            # weights (n[l] x n[l-1]), bias (n[l] x 1)
            W, b = self.model.unpack_params(l, params)
            # activation[l] (n(l) x m)
            Z.append(np.dot(W, A[l - 1]) + b)
            A.append(layer.activation[0](Z[l]))
            assert A[l].shape == (layer.dim, X.shape[1])
        return A, Z

    def _propagate_backward(self, params, A, Z, Y):
        m = A[-1].shape[1]
        grad = np.zeros(params.shape, dtype=np.float)
        # dJ/dA (1 x m)
        dA = -np.divide(Y, A[-1]) + np.divide(1 - Y, np.maximum(
            1 - A[-1], 1e-8))
        for l in reversed(range(1, len(self.model))):
            layer = self.model[l]
            # weights (n[l] x n[l-1]), bias (n[l] x 1)
            W, b = self.model.unpack_params(l, params)
            # dJ/dZ = dJ/dA * dA/dZ (n[l] x m)
            dZ = layer.activation[2](dA, Z[l])
            assert dZ.shape == A[l].shape
            # dJ/dW = dJ/dZ * dZ/dW (dim TBD)
            dW, db, dA_prev = self._linear_backward(dZ, A[l - 1], W, b)
            dA = dA_prev
            self.model.pack_params(l, grad, dW, db)
        return grad

    def _linear_backward(self, dZ, A_prev, W, b):
        m = A_prev.shape[1]
        dW = (1. / m) * np.dot(dZ, A_prev.T)
        dW += (self.lambd / m) * W
        db = (1. / m) * np.sum(dZ, axis=1, keepdims=True)
        dA_prev = np.dot(W.T, dZ)
        return dW, db, dA_prev


def load_dataset(file_name, prefix):
    model = h5py.File(file_name, 'r')
    X = np.array(model[prefix + '_x'][:], dtype=np.float)
    X = X.reshape((X.shape[0], -1)).T
    X = X / 255
    Y = np.array(model[prefix + '_y'][:], dtype=np.int)
    Y = Y.reshape((1, Y.shape[0]))
    return (X, Y)


def main():
    (train_X, train_Y) = load_dataset('datasets/images_train.h5', 'train_set')
    (test_X, test_Y) = load_dataset('datasets/images_test.h5', 'test_set')
    print('{} X{} Y{}'.format('train', train_X.shape, train_Y.shape))
    print('{} X{} Y{}'.format('test', test_X.shape, test_Y.shape))
    # Train model
    model = NnModel()
    model.add(16, 'relu', input_dim=train_X.shape[0])
    model.add(16, 'relu')
    model.add(16, 'relu')
    model.add(1, 'sigmoid')
    model.compile()
    optimizer = GradDescentOptimizer(iters=3000, alpha=0.01, debug=True)
    classifier = NnClassifier(model, optimizer, lambd=0.)
    start = time.time()
    costs = classifier.train(train_X, train_Y)
    end = time.time()
    # Compute predicitions
    Yp_train = classifier.predict(train_X)
    Yp_test = classifier.predict(test_X)
    print('train accuracy: {} %, took {}'.format(
        100 - np.mean(np.abs(Yp_train - train_Y)) * 100, end - start))
    print('test accuracy: {} %'.format(
        100 - np.mean(np.abs(Yp_test - test_Y)) * 100))
    # Plot cost
    plt.plot(np.squeeze(costs))
    plt.title('Learning rate = {}'.format(classifier.optimizer.alpha))
    plt.xlabel('iterations (per hundreds)')
    plt.ylabel('cost')
    plt.show()


main()
