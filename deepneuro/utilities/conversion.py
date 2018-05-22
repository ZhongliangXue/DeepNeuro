
import os
import numpy as np
import nibabel as nib
import nrrd
import dicom
import scipy
import subprocess

from collections import defaultdict
# from subprocess import call, PIPE

from deepneuro.utilities.util import grab_files_recursive


def _modify_dims(input_data, channels=False, batch=False, dim=None):

    return


def read_image_files(image_files, return_affine=False, channels=True, batch=False):

    # Rename this function to something more descriptive?

    if type(image_files) is np.ndarray:
        if return_affine:
            return image_files, None
        else:
            return image_files
    elif type(image_files) is str:
        image_files = [image_files]

    image_list = []
    affine = None
    for image_file in image_files:
        data, _, affine, _ = convert_input_2_numpy(image_file, return_all=True)
        image_list.append(data)
        
        # Badly presumes only one affine.

    if image_list[0].ndim == 4:
        array = np.rollaxis(np.stack([image for image in image_list], axis=-1), 3, 0)
    else:
        array = np.stack([image for image in image_list], axis=-1)

    # This is a little clunky.
    if return_affine:
        # This assumes all images share an affine matrix.
        # Replace with a better convert function, at some point.
        return array, affine
    else:
        return array


def get_dicom_pixel_array(dicom, filename):
    return dicom.pixel_array


def dcm_2_numpy(input_folder, verbose=False, harden_orientation=True, return_all=False):

    """ Uses pydicom to stack an alphabetical list of DICOM files. TODO: Make it
        take slice_order into account.
    """

    if verbose:
        print 'Searching for dicom files...'

    found_files = grab_files_recursive(input_folder)

    if verbose:
        print 'Found', len(found_files), 'in directory. \n'
        print 'Checking DICOM compatability...'

    dicom_files = []
    for file in found_files:
        try:
            temp_dicom = dicom.read_file(file)
            dicom_files += [[file, temp_dicom.data_element('SeriesInstanceUID').value]]
        except:
            continue

    if verbose:
        print 'Found', len(dicom_files), 'DICOM files in directory. \n'
        print 'Counting volumes..'

    unique_dicoms = defaultdict(list)
    for dicom_file in dicom_files:
        UID = dicom_file[1]
        unique_dicoms[UID] += [dicom_file[0]]

    if verbose:
        print 'Found', len(unique_dicoms.keys()), 'unique volumes \n'
        print 'Saving out files from these volumes.'

    for UID in unique_dicoms.keys():
    
        # Bad behavior: Currently outputs first DICOM found.
        # Unsure about error-checking with DICOM.

        if True:
        # try:
            # Grab DICOMs for a certain Instance
            current_files = unique_dicoms[UID]
            current_dicoms = [dicom.read_file(dcm) for dcm in unique_dicoms[UID]]
            # print current_files

            # Sort DICOMs by Instance.
            dicom_instances = [x.data_element('InstanceNumber').value for x in current_dicoms]
            current_dicoms = [x for _, x in sorted(zip(dicom_instances, current_dicoms))]
            current_files = [x for _, x in sorted(zip(dicom_instances, current_files))]
            first_dicom, last_dicom = current_dicoms[0], current_dicoms[-1]

            if verbose:
                print 'Loading...', input_folder

        # except:
        #     print 'Could not read DICOM volume SeriesDescription. Skipping UID...', str(UID)
        #     continue

        if True:
        # try:
            # Extract patient position information for affine creation.
            output_affine = np.eye(4)
            image_position_patient = np.array(first_dicom.data_element('ImagePositionPatient').value).astype(float)
            image_orientation_patient = np.array(first_dicom.data_element('ImageOrientationPatient').value).astype(float)
            last_image_position_patient = np.array(last_dicom.data_element('ImagePositionPatient').value).astype(float)
            pixel_spacing_patient = np.array(first_dicom.data_element('PixelSpacing').value).astype(float)

            # Create DICOM Space affine (don't fully understand, TODO)
            output_affine[0:3, 0] = pixel_spacing_patient[0] * image_orientation_patient[0:3]
            output_affine[0:3, 1] = pixel_spacing_patient[1] * image_orientation_patient[3:6]
            output_affine[0:3, 2] = (image_position_patient - last_image_position_patient) / (1 - len(current_dicoms))
            output_affine[0:3, 3] = image_position_patient

            # Transformations from DICOM to Nifti Space (don't fully understand, TOO)
            cr_flip = np.eye(4)
            cr_flip[0:2, 0:2] = [[0, 1], [1, 0]]
            neg_flip = np.eye(4)
            neg_flip[0:2, 0:2] = [[-1, 0], [0, -1]]
            output_affine = np.matmul(neg_flip, np.matmul(output_affine, cr_flip))

            # Create numpy array data...
            output_numpy = []
            for i in xrange(len(current_dicoms)):
                try:
                    output_numpy += [get_dicom_pixel_array(current_dicoms[i], current_files[i])]
                except:
                    print 'Warning, error at slice', i
            output_numpy = np.stack(output_numpy, -1)

            # If preferred, harden to identity matrix space (LPS, maybe?)
            # Also unsure of the dynamic here, but they work.
            if harden_orientation:

                cx, cy, cz = np.argmax(np.abs(output_affine[0:3, 0:3]), axis=0)

                output_numpy = np.transpose(output_numpy, (cx, cy, cz))

                harden_matrix = np.eye(4)
                for dim, i in enumerate([cx, cy, cz]):
                    harden_matrix[i, i] = 0
                    harden_matrix[dim, i] = 1
                output_affine = np.matmul(output_affine, harden_matrix)

                flip_matrix = np.eye(4)
                for i in xrange(3):
                    if output_affine[i, i] < 0:
                        flip_matrix[i, i] = -1
                        output_numpy = np.flip(output_numpy, i)

                output_affine = np.matmul(output_affine, flip_matrix)

            if return_all:
                return output_numpy, None, output_affine  # TODO provide DICOM tags without doubling memory
            else:
                return output_numpy

        # except:
            # print 'Could not read DICOM at folder...', input_folder


def itk_transform_2_numpy(input_filepath, return_all=False):

    """ This function takes in an itk transform text file and converts into a 4x4
        array.

        TODO: Ensure this correctly rotates.
        TODO: Make work for more than just .txt files.

        Parameters
        ----------
        filepath: str
            The filepath to be converted

        Returns
        -------
        output_array: numpy array
            A 4x4 float matrix containing the affine transform.
    """

    with open(input_filepath) as f:
        content = f.readlines()

    for row_idx, row in enumerate(content):
        if row.startswith("Parameters:"):
            r_idx = row_idx
        if row.startswith("FixedParameters:"):
            t_idx = row_idx

    output_array = np.zeros((4, 4))

    rotations = [float(r) for r in str.split(content[r_idx].replace("Parameters: ", '').rstrip(), ' ')]
    translations = [float(t) for t in str.split(content[t_idx].replace("FixedParameters: ", '').rstrip(), ' ')] + [1]

    for i in range(4):
        output_array[i, 0:3] = rotations[i * 3: (i + 1) * 3]
        output_array[i, 3] = translations[i]

    if return_all:
        return output_array, None, None
    else:
        return output_array


def img_2_numpy(input_image, return_all=False):
    
    """ Loads image data and returns a numpy array. There
        will likely be many parameters to specify because
        of the strange quantization issues seemingly inherent
        in loading images.
    """

    image_nifti = scipy.misc.imread(input_image)

    if return_all:
        return image_nifti, None, None
    else:
        return image_nifti


def nrrd_2_numpy(input_nrrd, return_all=False):
    
    """ Loads nrrd data and optionally return a nrrd header
        in pynrrd's format. If array is 4D, swaps axes so
        that time dimension is last to match nifti standard.
    """

    nrrd_data, nrrd_options = nrrd.read(input_nrrd)

    if nrrd_data.ndim == 4:
        nrrd_data = np.rollaxis(nrrd_data, 0, 4)

    if return_all:
        return nrrd_data, nrrd_options, None  # Affine not implemented yet..
    else:
        return nrrd_data


def nifti_2_numpy(input_filepath, return_all=False):

    """ Copies a file somewhere else. Effectively only used for compressing nifti files.

        Parameters
        ----------
        input_filepath: str
            Input filepath.
        return_header: bool
            If true, returns header information in nibabel format.

        Returns
        -------
        img: Numpy array
            Untransformed image data.
        header: list
            A two item list. The first is the affine matrix in array format, the
            second is 

    """

    nifti = nib.load(input_filepath)

    if return_all:
        return nifti.get_data(), nifti.header, nifti.affine
    else:
        return nifti.get_data()


def save_numpy_2_nifti(image_numpy, reference_nifti_filepath=None, output_filepath=None, metadata=None):

    """ This is a bit convoluted.

        TODO: Documentation, rearrange reference_nifti and output_filepath, and
        propagate changes to the rest of qtim_tools.
    """

    if reference_nifti_filepath is not None:
        if isinstance(reference_nifti_filepath, basestring):
            nifti_image = nib.load(reference_nifti_filepath)
            image_affine = nifti_image.affine
        else:
            image_affine = reference_nifti_filepath
    else:
        image_affine = np.eye(4)

    output_nifti = nib.Nifti1Image(image_numpy, image_affine)

    if output_filepath is None:
        return output_nifti
    else:
        nib.save(output_nifti, output_filepath)
        return output_filepath


# Consider merging these into one dictionary. Separating them is easier to visaulize though.
FORMAT_LIST = {'dicom': ('.dcm', '.ima'), 
                'nifti': ('.nii', '.nii.gz'), 
                'nrrd': ('.nrrd', '.nhdr'), 
                'image': ('.jpg', '.png'), 
                'itk_transform': ('.txt', '.tfm')}

NUMPY_CONVERTER_LIST = {'dicom': dcm_2_numpy, 
                'nifti': nifti_2_numpy, 
                'nrrd': nrrd_2_numpy, 
                'image': img_2_numpy, 
                'itk_transform': itk_transform_2_numpy}

SAVE_EXPORTER_LIST = {'nifti': save_numpy_2_nifti}


def check_format(filepath):

    format_type = None

    if os.path.isdir(filepath):
        format_type = 'dicom'
    else:
        for data_type in FORMAT_LIST:
            if filepath.lower().endswith(FORMAT_LIST[data_type]):
                format_type = data_type
            if format_type is not None:
                break

    if format_type is None:
        raise ValueError
        # print 'Error! Input file extension is not supported by qtim_tools. Returning None.'
    else:
        return format_type


def convert_input_2_numpy(input_data, input_format=None, return_all=False):
    
    """ Copies a file somewhere else. Effectively only used for compressing nifti files.

        Note: Some say it is bad practice to have varying amounts of objects returned. On
        the other hand, I find it easier to use this way.

        Parameters
        ----------
        input_filepath: str
            Input filepath.
        return_header: bool
            If true, returns header information in nibabel format.

        Returns
        -------
        img: Numpy array
            Untransformed image data.
        header: list
            Varies from format to format.
        type: str
            Internal code for image type.
    """

    if isinstance(input_data, basestring):
        if input_format is None:
            input_format = check_format(input_data)

        if input_format is None:
            raise ValueError
            if return_all:
                return None, None, None, None
            else:
                return None

        if return_all:
            return NUMPY_CONVERTER_LIST[input_format](input_data, return_all=True) + (input_format,)
        else:
            return NUMPY_CONVERTER_LIST[input_format](input_data)

    else:
        if return_all:
            return input_data, None, None, 'numpy'
        else:
            return input_data


def save_data(input_data, output_filename, reference_data=None, metadata=None, affine=None, output_format='.nii.gz'):

    """ This is a bit convoluted.

        TODO: Documentation, rearrange reference_nifti and output_filepath, and
        propagate changes to the rest of qtim_tools.
    """

    output_filetype = check_format(output_format)

    if isinstance(input_data, str) and output_filetype is not 'text':
        input_data, metadata, reference_data, data_format = convert_input_2_numpy(input_data, return_all=True)

    return SAVE_EXPORTER_LIST[output_filetype](input_data, reference_data, output_filename, metadata)


def execute(cmd):
    popen = subprocess.Popen(cmd, stdout=subprocess.PIPE, universal_newlines=True)
    for stdout_line in iter(popen.stdout.readline, ""):
        yield stdout_line 
    popen.stdout.close()
    return_code = popen.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, cmd)


def save_input_2_dso(input_data, reference_dicom_filepath, dso_metadata, reference_nifti_filepath=None, output_filepath=None, command='/home/abeers/Software/dcmqi-1.0.9-linux/bin/itkimage2segimage', verbose=True):

    """ Given an DICOM directory to reference and a list of files (and in the future Nifti files), save these files
       to a DSO object.
   """

    reference_dicom_filepath = os.path.abspath(reference_dicom_filepath)
    output_filepath = os.path.abspath(output_filepath)
    dso_metadata = os.path.abspath(dso_metadata)

    base_command = [command, '--inputDICOMDirectory', reference_dicom_filepath, '--outputDICOM', output_filepath, '--inputMetadata', dso_metadata, '--inputImageList']

    if type(input_data) is not list:
        input_data = [input_data]

    input_data_string = ''
    for data_object in input_data:

        if input_data_string != '':
            input_data_string += ','

        # Check this typing syntax for Python 3
        if type(data_object) is str:
            data_object = os.path.abspath(data_object)
            input_data_string += data_object
        else:
            pass
            # TODO: Put in utility for converting numpy to DSO.

    base_command += [input_data_string]

    subprocess.call(' '.join(base_command), shell=True)

    return output_filepath