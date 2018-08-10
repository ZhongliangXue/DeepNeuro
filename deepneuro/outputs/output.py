import os
import numpy as np

from deepneuro.utilities.conversion import save_numpy_2_nifti, save_data
from deepneuro.utilities.util import add_parameter, replace_suffix, nifti_splitext


class Output(object):

    def __init__(self, **kwargs):

        # Data Parameters
        add_parameter(self, kwargs, 'data_collection', None)
        add_parameter(self, kwargs, 'inputs', ['input_modalities'])
        add_parameter(self, kwargs, 'ground_truth', ['ground_truth'])

        # Saving Parameters
        add_parameter(self, kwargs, 'save_to_file', True)
        add_parameter(self, kwargs, 'save_initial', True)
        add_parameter(self, kwargs, 'save_all_steps', False)
        add_parameter(self, kwargs, 'output_directory', None)
        add_parameter(self, kwargs, 'output_filename', 'prediction.nii.gz')
        add_parameter(self, kwargs, 'stack_outputs', False)

        # Implementation Parameters
        add_parameter(self, kwargs, 'channels_first', False)
        add_parameter(self, kwargs, 'batch_size', 32)

        # Internal Parameters
        add_parameter(self, kwargs, 'replace_existing', True)
        add_parameter(self, kwargs, 'verbose', True)
        add_parameter(self, kwargs, 'case', None)

        # Derived Parameters
        self.return_objects = []
        self.return_filenames = []
        self.postprocessors = []
        self.postprocessor_string = ''

        self.load(kwargs)

        return

    def load(self, kwargs):

        """ This method is used by children classes to load additional attributes from kwargs. These
            may be parameters specific to a certain model type, for example.
        """

        return

    def execute(self, model):

        return None

    def append_postprocessor(self, postprocessors):

        if type(postprocessors) is not list:
            postprocessors = [postprocessors]

        for postprocessor in postprocessors:
            self.postprocessors += [postprocessor]

        return None

    def generate(self):

        # Very ambiguous naming scheme here.
        # The conditionals are a little cagey here.
        # Also the duplicated code.

        # Create output directory. If not provided, output into original patient folder.
        if self.output_directory is not None:
            if not os.path.exists(self.output_directory):
                os.makedirs(self.output_directory)

        if self.case is None:

            # At present, this only works for one input, one output patch networks.
            data_generator = self.data_collection.data_generator(verbose=True)

            input_data = next(data_generator)
            
            while input_data is not None:
                self.return_objects = []
                self.return_filenames = []
                self.process_case(input_data[self.inputs[0]])
                self.postprocess()
                input_data = next(data_generator)

        else:
            self.return_objects = []
            self.return_filenames = []
            self.process_case(self.data_collection.get_data(self.case))
            self.postprocess()         

        return_dict = {'data': self.return_objects, 'filenames': self.return_filenames}
        return return_dict

    def postprocess(self):

        if self.save_to_file and (self.save_initial or self.postprocessors == []):
            self.save_output()

        for p_idx, postprocessor in enumerate(self.postprocessors):
            postprocessor.execute(self)
            if self.save_all_steps and p_idx != len(self.postprocessors) - 1:
                self.save_output(postprocessor)

        if self.save_to_file and self.postprocessors != []:
            self.save_output(self.postprocessors[-1])

    def save_output(self, postprocessor=None):

        # Currently assumes Nifti output. TODO: Make automatically detect output or determine with a class variable.
        # Ideally, split also this out into a saving.py function in utils.
        # Case naming is a little wild here, TODO: make more simple.

        for input_data in self.return_objects:

            casename = self.data_collection.data_groups[self.inputs[0]].base_casename
            input_affine = self.data_collection.data_groups[self.inputs[0]].base_affine

            augmentation_string = self.data_collection.data_groups[self.inputs[0]].augmentation_strings[-1]

            if self.output_directory is None:
                output_directory = casename
            else:
                output_directory = self.output_directory

            if os.path.exists(casename) and not os.path.isdir(casename):
                output_filename = os.path.basename(nifti_splitext(casename)[0]) + self.output_filename
            else:
                output_filename = self.output_filename

            if postprocessor is None:
                output_filepath = os.path.join(output_directory, replace_suffix(output_filename, '', augmentation_string + self.postprocessor_string))
            else:
                output_filepath = os.path.join(output_directory, replace_suffix(output_filename, '', augmentation_string + postprocessor.postprocessor_string))

            # If prediction already exists, skip it. Useful if process is interrupted.
            if os.path.exists(output_filepath) and not self.replace_existing:
                return

            # Squeezing is a little cagey. Maybe explicitly remove batch dimension instead.
            output_shape = input_data.shape
            input_data = np.squeeze(input_data)

            print np.unique(input_data)

            return_filenames = []

            # If there is only one channel, only save one file.
            if output_shape[-1] == 1 or self.stack_outputs:
                self.return_filenames += [save_data(input_data, output_filepath, affine=input_affine)]

            else:
                for channel in range(output_shape[-1]):
                    return_filenames += [save_numpy_2_nifti(input_data[..., channel], input_affine, output_filepath=replace_suffix(output_filepath, input_suffix='', output_suffix='_channel_' + str(channel)))]
                self.return_filenames += [return_filenames]

        return

