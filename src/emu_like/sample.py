"""
.. module:: sample

:Synopsis: Module with the Sample class, dealing samples of data.
:Author: Emilio Bellini

"""

import numpy as np
import os
import re
import tqdm
import sklearn.model_selection as skl_ms
from . import sampling_functions as fng  # noqa:F401
from . import defaults as de
from . import io as io
from . import scalers as sc
from . import samplers as smp
from .params import Params


class Sample(object):
    """
    Base class to deal with samples.
    Available methods:
    - load: load a sample from a path;
    - save: save a sample into a folder;
    - generate: generate a sample from a dictionary of settings;
    - resume: after loading a function, if it is incomplete, it
      computes the remaining samples;
    - join: if they are compatible, join two samples and return a single one;
    - train_test_split: split sample into train and test samples;
    - rescale: rescale sample (both x and y);
    - get_plots: get plots of sample.

    NOTE: the samples generated by this code contain one file
    for the x points, one for y, and one with all the settings.
    The x and y files have the name of the variables on their header.
    For flexibility, i.e. when they were created from other codes,
    the samples can have two other formats:
    - they can be loaded from two separate files (one for x and one
      for y) without a settings file.
    - they can be loaded from a single file containing both x and y.
      In this case the default behaviour is that the last column is y,
      and the remaining are all x's.
    In all these cases, it is possible to select which columns to load
    for x and for y.

    NOTE: the name of the files of the generated samples can be found
    in 'src/emu_like/defaults.py'.
    """

    def __init__(self):
        """
        Placeholders.
        """
        self.x = None  # Array with x data
        self.y = None  # Array with y data
        self.x_names = None  # List of names of x data
        self.y_names = None  # List of names of y data
        self.n_samples = None  # Number of samples
        self.n_x = None  # Number of x variables
        self.n_y = None  # Number of y variables
        self.settings = None  # Settings dictionary
        self.path = None  # Path of the sample
        self.x_train = None  # Array with x_train data
        self.y_train = None  # Array with y_train data
        self.x_test = None  # Array with x_test data
        self.y_test = None  # Array with y_test data
        self.x_ranges = None  # Range of x data
        return

    def _load_array(self, path, columns):
        """
        Load an array from file.
        Arguments:
        - path (str): path to the array
        - columns: slice object or list of column indices to be read
        - verbose (bool, default: False): verbosity.
        """
        array = np.genfromtxt(path)
        # Adjust array dimensions.
        # If it has one feature I still want 1x2_samples
        if array.ndim == 1:
            array = array[:, np.newaxis]
        names = self._try_to_load_names_array(path, n_names=array.shape[1])
        array = array[:, columns]
        try:
            names = names[columns]
        except TypeError:
            pass
        return array, names

    def _try_to_load_names_array(self, path, n_names=None,
                                 comments='#', delimiter='\t'):
        """
        Try to load name of parameters from array.
        Names are extracted from the last comment row
        (starting with 'comments') of the file and should
        match the number of columns of the array.
        Arguments:
        - path (str): path to the array;
        - n_names (int, default: None): number of names to
          be expected. It is used to validate the extracted names.
          If they do not match, this method returns None;
        - comments (str, default: '#'). Starting string for comments;
        - delimiter (str, default: '\t'). Separator for column names.

        """
        is_comment = True
        names = None
        # Look for the last line that starts with 'comments'
        with open(path, 'r') as fn:
            while is_comment:
                line = fn.readline()
                if line.startswith(comments):
                    names = line
                else:
                    is_comment = False
        # Split names
        try:
            names = re.sub(comments, '', names)
        except TypeError:
            return None
        names = names.split(delimiter)
        names = np.array([x.strip() for x in names])
        # Check names have the right dimensions
        if n_names:
            if n_names == len(names):
                return names
            else:
                return None
        return names

    def _save_settings(self, path, verbose=False):
        """
        Quick way to save settings dictionary in path.
        Arguments:
        - path (str): folder where to store settings;
        - verbose (bool, default: False): verbosity.

        NOTE: this assumes that settings is already an
        attribute of the class, and saves them with the
        default name and header.
        """
        params = Params(content=self.settings)
        params.save(
            de.file_names['params']['name'],
            root=path,
            header=de.file_names['params']['header'],
            verbose=verbose)
        return

    def _save_x(self, path, verbose=False):
        """
        Quick way to save x array in path.
        Arguments:
        - path (str): folder where to store x array;
        - verbose (bool, default: False): verbosity.

        NOTE: this assumes that x is already an attribute
        of the class, and saves it with the default
        name and header.
        """
        fpath = os.path.join(path, de.file_names['x_sample']['name'])
        if verbose:
            io.print_level(1, 'Saved x array at: {}'.format(fpath))
        np.savetxt(fpath, self.x, header='\t'.join(self.x_names))
        return

    def _save_y(self, path, verbose=False):
        """
        Quick way to save y array in path.
        Arguments:
        - path (str): folder where to store y array;
        - verbose (bool, default: False): verbosity.

        NOTE: this assumes that y is already an attribute
        of the class, and saves it with the default
        name and header.
        """
        fpath = os.path.join(path, de.file_names['y_sample']['name'])
        try:
            header = '\t'.join(self.y_names)
        except TypeError:
            header = ''
        if verbose:
            io.print_level(1, 'Saved y array at: {}'.format(fpath))
        np.savetxt(fpath, self.y, header=header)
        return

    def _append_y(self, path, y_val):
        """
        Quick way to append rows to the y array in path.
        Arguments:
        - path (str): folder where the y array is stored;
        - verbose (bool, default: False): verbosity.
        """
        fpath = os.path.join(path, de.file_names['y_sample']['name'])
        with open(fpath, 'a') as fn:
            np.savetxt(fn, [y_val])
        return

    def _is_varying(self, params, param):
        """
        Return True if param has key 'prior',
        False otherwise.
        """
        if isinstance(params[param], dict):
            if 'prior' in params[param].keys():
                return True
        return False

    def load(self,
             path,
             path_y=None,
             columns_x=slice(None),
             columns_y=slice(None),
             remove_non_finite=False,
             verbose=False):
        """
        Load an existing sample.
        Arguments:
        - path (str): path pointing to the folder containing the sample,
          or to a file containing the x data. If y data are in the same
          this is sufficient, otherwise 'path_y' should be specified. See
          discussion at the top of this Class for possible input samples;
        - path_y (str, default: None): in case x and y data are stored
          in different files and different folders, use this variable
          to specify the file containing the y data;
        - columns_x (list of indices or slice object). Default: if x and y
          data come from different files all columns. If x and y are in
          the same file, all columns except the last one;
        - columns_y (list of indices or slice object). Default: if x and y
          data come from different files all columns. If x and y are in
          the same file, last column;
        - remove_non_finite (bool, default: False). Remove all rows where
          any of the y's is non finite (infinite or nan);
        - verbose (bool, default: False): verbosity.

        NOTE: when generated by this code, the sample files have specific
        names (see discussion at the top of this Class). One case where it
        is necessary to specify both 'path' and 'path_y' is when the input
        files do not have the defaults names.
        """

        if verbose:
            io.info('Loading sample.')

        # Load settings, if any
        path_settings = os.path.join(path, de.file_names['params']['name'])
        try:
            self.settings = Params().load(path_settings)
        except NotADirectoryError:
            io.warning('Unable to load parameter file!')

        # Assign paths to x and y. There are two cases:
        # 1) Two files for x and y
        if path and path_y:
            path_x = path
            path_y = path_y
        # 2) One directory with two files for x and y
        elif os.path.isdir(path):
            path_x = os.path.join(path, de.file_names['x_sample']['name'])
            path_y = os.path.join(path, de.file_names['y_sample']['name'])
            # Save folder path attribute. We need it to resume sample.
            # This case is the standard output of 'generate' and it is
            # the only one for which resume works.
            self.path = path
        # 3) One file for x and y
        elif os.path.isfile(path):
            # Change default columns
            columns_x = slice(None, -1)
            columns_y = slice(-1, None)
            path_x = path
            path_y = path
        else:
            raise FileNotFoundError(
                'Something is wrong with your sample path. I could not '
                'identify the x and y paths')

        # Load data
        self.x, self.x_names = self._load_array(path_x, columns_x)
        self.y, self.y_names = self._load_array(path_y, columns_y)
        self.x_ranges = list(zip(np.min(self.x, axis=0),
                                 np.max(self.x, axis=0)))

        # Remove non finite if requested
        if remove_non_finite:
            if verbose:
                io.info('Removing non finite data from sample.')
            only_finites = np.any(np.isfinite(self.y), axis=1)
            self.x = self.x[only_finites]
            self.y = self.y[only_finites]

        # Get sample attributes
        self.n_samples = self.x.shape[0]
        self.n_x = self.x.shape[1]
        self.n_y = self.y.shape[1]

        # Print info
        if verbose:
            io.print_level(1, 'Parameters from: {}'.format(path_settings))
            io.print_level(1, 'x from: {}'.format(path_x))
            io.print_level(1, 'y from: {}'.format(path_y))
            io.print_level(1, 'n_samples: {}'.format(self.n_samples))
            io.print_level(1, 'n_x: {}'.format(self.n_x))
            io.print_level(1, 'n_y: {}'.format(self.n_y))

        return self

    def save(self, path, verbose=False):
        """
        Save sample to path.
        - path (str): output path;
        - verbose (bool, default: False): verbosity.
        """
        self.path = path

        if verbose:
            io.print_level(1, 'Saving output at: {}'.format(path))

        # Create main folder
        io.Folder(path).create(verbose=verbose)

        # Save settings
        self._save_settings(path, verbose=False)

        # Save x
        self._save_x(path, verbose=False)

        # Save y
        self._save_y(path, verbose=False)

        return

    def generate(self, params, sampled_function, n_samples, spacing,
                 save_incrementally=False, output_path=None, verbose=False):
        """
        Generate a sample.
        Arguments:
        - params (dict): dictionary containing the parameters to be passed
          to the sampled_function. See simple_sample.yaml and
          planck_sample.yaml for details;
        - sampled_function (str): one of the functions defined in
          src/emu_like/sampling_functions.py;
        - n_samples (int): number of samples to compute;
        - spacing (str): spacing of the sample. Options are those defined in
          src/emu_like/samplers.py;
        - save_incrementally (bool, default: False): save output incrementally;
        - output_path (str, default: None): if save_incrementally the output
          path should be passed;
        - verbose (bool, default: False): verbosity.
        """

        if verbose:
            io.info('Generating sample.')
            io.print_level(1, 'Sampled function: {}'.format(sampled_function))
            io.print_level(1, 'Number of samples: {}'.format(n_samples))
            io.print_level(1, 'Spacing: {}'.format(spacing))

        # Create main folder
        if save_incrementally:
            self.path = output_path
            io.Folder(output_path).create(verbose=verbose)

        # Create settings dictionary
        if sampled_function == 'cobaya_loglike':
            params_name = 'cobaya'
        else:
            params_name = 'params'
        self.settings = {
            params_name: params,
            'sampled_function': sampled_function,
            'n_samples': n_samples,
            'spacing': spacing,
        }
        # Save settings
        if save_incrementally:
            self._save_settings(output_path, verbose=verbose)

        # Function to be sampled
        fun = eval('fng.' + sampled_function)

        # Get correct parameters to be passed to fun
        if sampled_function == 'cobaya_loglike':
            sampled_params = params['params']
        else:
            sampled_params = params

        # Get x names
        self.x_names = [x for x in sampled_params
                        if self._is_varying(sampled_params, x)]

        # Get x array
        x_sampler = smp.Sampler().choose_one(spacing, verbose=verbose)
        self.x = x_sampler.get_x(sampled_params, self.x_names, n_samples)
        self.n_x = self.x.shape[1]
        # Save x array
        if save_incrementally:
            self._save_x(output_path, verbose=verbose)

        # Get first sampled y (to retrieve y_names and model)
        y_val, self.y_names, model = fun(self.x[0], self.x_names, params)
        self.y = [y_val]
        # Save y array (first row, then we update it)
        if save_incrementally:
            self._save_y(output_path, verbose=verbose)

        # Sample y
        for x in tqdm.tqdm(self.x[1:]):
            y_val, _, _ = fun(x, self.x_names, params, model=model)
            self.y.append(y_val)
            if save_incrementally:
                self._append_y(output_path, y_val)

        self.y = np.array(self.y)
        self.n_y = self.y.shape[1]
        return

    def resume(self, save_incrementally=False, verbose=False):
        """
        Resume a sample previously loaded (use load method
        before resuming). Many settings are already loaded.
        Arguments:
        - save_incrementally (bool, default: False): save output incrementally;
        - verbose (bool, default: False): verbosity.

        NOTE: this method assumes that both settings and the fulle x array
        are already saved into the folder. The x array is then used to
        calculate the missing row of the y array.
        """

        remaining_steps = self.settings['n_samples']-self.y.shape[0]
        if verbose:
            io.info('Resuming sample.')
            io.print_level(1, 'Sampled function: {}'
                           ''.format(self.settings['sampled_function']))
            io.print_level(
                1, 'Missing samples: {}'
                ''.format(remaining_steps))
            io.print_level(1, 'Spacing: {}'.format(self.settings['spacing']))
        if remaining_steps == 0:
            if verbose:
                io.warning('Sample complete, nothing to resume!')
            return

        # Function to be sampled
        fun = eval('fng.' + self.settings['sampled_function'])

        #
        if self.settings['sampled_function'] == 'cobaya_loglike':
            params = self.settings['cobaya']
        else:
            params = self.settings['params']

        # Get first sampled y (to retrieve model)
        _, _, model = fun(self.x[0], self.x_names, params)

        # Sample y
        for x in tqdm.tqdm(self.x[self.y.shape[0]:]):
            y_val, _, _ = fun(x, self.x_names, params, model=model)
            self.y = np.vstack((self.y, y_val))
            if save_incrementally:
                self._append_y(self.path, y_val)
        return

    @staticmethod
    def join(samples, verbose=False):
        """
        Join a list of Sample into a unique one.
        This defines the minimum number of attributes
        required to use a sample for tranining, i.e.
        x, y, n_x, n_y, n_samples, x_names and y_names.
        Before joining them it checks that n_x and n_y are
        the same for each sample.
        Arguments:
        - samples (list of Sample): list of Sample classes (already loaded);
        - verbose (bool, default: False): verbosity.
        """

        if verbose:
            io.info('Joining samples')
            for sample in samples:
                io.print_level(1, '{}'.format(sample.path))

        sample = Sample()

        # n_x
        if all(s.n_x == samples[0].n_x for s in samples):
            sample.n_x = samples[0].n_x
        else:
            raise ValueError('Samples can not be joined as they have '
                             'different number of x variables')

        # n_y
        if all(s.n_y == samples[0].n_y for s in samples):
            sample.n_y = samples[0].n_y
        else:
            raise ValueError('Samples can not be joined as they have '
                             'different number of x variables')

        # x array
        total = tuple([s.x for s in samples])
        sample.x = np.vstack(total)
        sample.x_ranges = np.stack((
            np.min(sample.x, axis=0),
            np.max(sample.x, axis=0))).T

        # y array
        total = tuple([s.y for s in samples])
        sample.y = np.vstack(total)

        # x and y names
        sample.x_names = samples[0].x_names
        sample.y_names = samples[0].y_names

        # n_samples
        sample.n_samples = sum([s.n_samples for s in samples])
        return sample

    def train_test_split(self, frac_train, seed, verbose=False):
        """
        Split a sample into test and train samples.
        The split is stored into the x_train, x_test,
        y_train and y_test attributes.
        Arguments:
        - frac_train (float): fraction of training samples (between 0 and 1);
        - seed (int): seed to randomly split train and test;
        - verbose (bool, default: False): verbosity.

        NOTE: this method assumes that both settings and the fulle x array
        are already saved into the folder. The x array is then used to
        calculate the missing row of the y array.
        """

        if verbose:
            io.info('Splitting training and testing samples.')
            io.print_level(1, 'Fractional number of training samples: {}'
                           ''.format(frac_train))
            io.print_level(1, 'Random seed for train/test split: '
                           '{}'.format(seed))
        split = skl_ms.train_test_split(self.x, self.y,
                                        train_size=frac_train,
                                        random_state=seed)
        self.x_train, self.x_test, self.y_train, self.y_test = split
        return

    def rescale(self, rescale_x, rescale_y, verbose=False):
        """
        Rescale x and y of a sample. The available scalers are
        written in src/emu_like/scalers.py
        Arguments:
        - rescale_x (str): scaler for x;
        - rescale_x (str): scaler for y;
        - verbose (bool, default: False): verbosity.

        NOTE: this method assumes that we already splitted
        train and test samples.
        """

        if verbose:
            io.info('Rescaling x and y.')
            io.print_level(1, 'x with: {}'.format(rescale_x))
            io.print_level(1, 'y with: {}'.format(rescale_y))
        # Rescale x
        self.x_scaler = sc.Scaler.choose_one(rescale_x)
        self.x_scaler.fit(self.x_train)
        self.x_train_scaled = self.x_scaler.transform(self.x_train)
        self.x_test_scaled = self.x_scaler.transform(self.x_test)
        # Rescale y
        self.y_scaler = sc.Scaler.choose_one(rescale_y)
        self.y_scaler.fit(self.y_train)
        self.y_train_scaled = self.y_scaler.transform(self.y_train)
        self.y_test_scaled = self.y_scaler.transform(self.y_test)
        if verbose:
            io.print_level(1, 'Rescaled bounds:')
            mins = np.min(self.x_train_scaled, axis=0)
            maxs = np.max(self.x_train_scaled, axis=0)
            for nx, min in enumerate(mins):
                io.print_level(
                    2, 'x_train_{} = [{}, {}]'.format(nx, min, maxs[nx]))
            mins = np.min(self.x_test_scaled, axis=0)
            maxs = np.max(self.x_test_scaled, axis=0)
            for nx, min in enumerate(mins):
                io.print_level(
                    2, 'x_test_{} = [{}, {}]'.format(nx, min, maxs[nx]))
            mins = np.min(self.y_train_scaled, axis=0)
            maxs = np.max(self.y_train_scaled, axis=0)
            for nx, min in enumerate(mins):
                io.print_level(
                    2, 'y_train_{} = [{}, {}]'.format(nx, min, maxs[nx]))
            mins = np.min(self.y_test_scaled, axis=0)
            maxs = np.max(self.y_test_scaled, axis=0)
            for nx, min in enumerate(mins):
                io.print_level(
                    2, 'y_test_{} = [{}, {}]'.format(nx, min, maxs[nx]))
        return
