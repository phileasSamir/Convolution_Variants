"""Tests Augmented Attention Layer.

Mainly tests for shape correctness.
"""

import unittest
import os
import argparse

os.environ["CUDA_VISIBLE_DEVICES"] = '1'
os.environ['TF_FORCE_GPU_ALLOW_GROWTH'] = 'true'

import tensorflow as tf
from tensorflow.keras.layers import Dense, Flatten, Conv2D
from tensorflow.keras import Model
import numpy as np

import convVariants

randomItem = np.random.random_sample
getShape = lambda input_: tuple(input_.shape)

class MNISTModel(Model):
    def __init__(self, conv_layer):
        super(MNISTModel, self).__init__()
        self.conv = conv_layer
        self.flatten = Flatten()
        self.d1 = Dense(128, activation='relu')
        self.d2 = Dense(10, activation='softmax')

    def call(self, x):
        x = self.conv(x)
        x = self.flatten(x)
        x = self.d1(x)
        return self.d2(x)

# @unittest.skip('Correct')
class TestCustomConv(unittest.TestCase):

    def MNIST_load_data(self, max_instances, repeats):
        (x_train, y_train), (x_test, y_test) = tf.keras.datasets.mnist.load_data()

        x_train, x_test = x_train / 255.0, x_test / 255.0
        x_train = x_train[:, tf.newaxis, :, :]
        x_test = x_test[:, tf.newaxis, :, :]

        x_train = x_train[:max_instances]
        y_train = y_train[:max_instances]
        x_test = x_test[:max_instances]
        y_test = y_test[:max_instances]

        x_train = np.repeat(x_train, repeats=repeats, axis=1)
        x_test = np.repeat(x_test, repeats=repeats, axis=1)

        return x_train, y_train, x_test, y_test


    def MNIST_run(
        self, 
        layer, 
        max_instances=1000, 
        EPOCHS=2, 
        repeats=1, 
        verbose=True):
        """This is just to check if the layer is backpropable.
        """
    
        x_train, y_train, x_test, y_test = self.MNIST_load_data(
            max_instances,
            repeats)

        train_ds = tf.data.Dataset.from_tensor_slices(
            (x_train, y_train)).shuffle(1000).batch(32)

        test_ds = tf.data.Dataset.from_tensor_slices(
            (x_test, y_test)).batch(32)

        model = MNISTModel(layer)

        loss_object = tf.keras.losses.SparseCategoricalCrossentropy()
        optimizer = tf.keras.optimizers.Adam()

        train_loss = tf.keras.metrics.Mean(name='train_loss')
        train_accuracy = tf.keras.metrics.SparseCategoricalAccuracy(
            name='train_accuracy')

        test_loss = tf.keras.metrics.Mean(name='test_loss')
        test_accuracy = tf.keras.metrics.SparseCategoricalAccuracy(
            name='test_accuracy')

        @tf.function
        def train_step(images, labels):
            with tf.GradientTape() as tape:
                predictions = model(images)
                loss = loss_object(labels, predictions)
            gradients = tape.gradient(loss, model.trainable_variables)
            optimizer.apply_gradients(zip(gradients, model.trainable_variables))

            train_loss(loss)
            train_accuracy(labels, predictions)

        @tf.function
        def test_step(images, labels):
            predictions = model(images)
            t_loss = loss_object(labels, predictions)

            test_loss(t_loss)
            test_accuracy(labels, predictions)

        for epoch in range(EPOCHS):
            for images, labels in train_ds:
                train_step(images, labels)

            for test_images, test_labels in test_ds:
                test_step(test_images, test_labels)

            if verbose:
                template = 'Epoch {}, Loss: {}, Accuracy: {}, \
                    Test Loss: {}, Test Accuracy: {}'
                print(template.format(epoch+1,
                    train_loss.result(),
                    train_accuracy.result()*100,
                    test_loss.result(),
                    test_accuracy.result()*100))

            # Reset the metrics for the next epoch
            train_loss.reset_states()
            train_accuracy.reset_states()
            test_loss.reset_states()
            test_accuracy.reset_states()

    
    def MNIST_run2(self, layer, max_instances=1000, EPOCHS=2, repeats=1):
        """This doesn't work if output shapes are undetermined. """

        x_train, y_train, x_test, y_test = self.MNIST_load_data(
            max_instances,
            repeats)

        model = tf.keras.models.Sequential([
            layer,
            tf.keras.layers.Flatten(),
            tf.keras.layers.Dense(128, activation='relu'),
            tf.keras.layers.Dropout(0.2),
            tf.keras.layers.Dense(10, activation='softmax')
            ])

        model.compile(
            optimizer='adam',
            loss='sparse_categorical_crossentropy',
            metrics=['accuracy'])

        model.fit(x_train, y_train, epochs=EPOCHS)

        model.evaluate(x_test,  y_test, verbose=2)


    @unittest.skip('Correct')
    def test_AAConv(self):

        H = 36
        W = 54
        C_IN = 6
        C_OUT = 53
        B = 3
        kernel_size = 5
        depth_k = 16
        depth_v = 24
        num_heads = 8

        AAlayer = convVariants.AAConv(
            channels_out=C_OUT,
            kernel_size=kernel_size,
            depth_k=depth_k,
            depth_v=depth_v,
            num_heads=num_heads)

        input_shape = (B, C_IN, H, W)
        AAlayer.build(input_shape)

        x = randomItem((B, depth_k, H, W))
        result = AAlayer._split_heads_2d(x)
        self.assertEqual(
            getShape(result),
            (B, num_heads, H, W, depth_k // num_heads))

        x = randomItem((B, num_heads, H, W, depth_k // num_heads))
        result = AAlayer._combine_heads_2d(x)
        self.assertEqual(
            getShape(result),
            (B, H, W, depth_k))

        x = randomItem((B, C_IN, H, W))
        result = AAlayer._self_attention_2d(x)
        self.assertEqual(
            getShape(result),
            (B, depth_v, H, W))

        x = randomItem(input_shape)
        result = AAlayer(x)
        self.assertEqual(
            getShape(result),
            (B, C_OUT, H, W))

        layer = convVariants.AAConv(
            channels_out=32,
            kernel_size=3,
            depth_k=8, 
            depth_v=8, 
            num_heads=4)

        self.MNIST_run(layer)

           
    @unittest.skip('Correct.')
    def test_MixConv(self):
        H = 36
        W = 54
        C_IN = 49
        C_OUT = 53
        B = 3

        expected_num_in_channels = [13, 12, 12, 12]
        input_shape = (B, C_IN, H, W)
        

        def check_depthwise(depthwise):

            kernel_sizes = [5, 7, 9, 11]
            layer = convVariants.MixConv(
                C_OUT, 
                kernel_sizes,
                depthwise=depthwise)
            layer.build(input_shape)

            result = layer._split_channels(C_IN, len(kernel_sizes))
            self.assertEqual(
                result,
                expected_num_in_channels)

            x = randomItem(input_shape)
            result = layer(x)
            self.assertEqual(
                getShape(result),
                (B, C_OUT, H, W))

            kernel_sizes = [3, 5]
            layer = convVariants.MixConv(
                C_OUT, 
                kernel_sizes,
                depthwise=depthwise)

            self.MNIST_run2(layer, repeats=3)

        check_depthwise(True)
        check_depthwise(False)




if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description='Testing custom convolution layers. Includes: \n \
            Augmented Attention Convolution \n \
            Mixed Depthwise Convolution')

    parser.add_argument(
        '-E', '--eager', default=False,
        help='Whether to test AAConv.py with eager execution or not.')

    args = parser.parse_args()

    if args.eager:
        tf.config.experimental_run_functions_eagerly(True)

    unittest.main()