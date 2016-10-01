"""
This pipeline is used to classify enhacement signals have been normalized and
projected using kernel PCA.
"""

import os

import numpy as np

from sklearn.decomposition import KernelPCA
from sklearn.externals import joblib
from sklearn.preprocessing import label_binarize

from protoclass.data_management import DCEModality
from protoclass.data_management import GTModality

from protoclass.preprocessing import StandardTimeNormalization

from protoclass.extraction import EnhancementSignalExtraction

from protoclass.classification import Classify

# Define the path where all the patients are
path_patients = '/data/prostate/experiments'
# Define the path of the modality to normalize
path_dce = 'DCE_reg_bspline'
# Define the path of the ground for the prostate
path_gt = ['GT_inv/prostate', 'GT_inv/pz', 'GT_inv/cg', 'GT_inv/cap']
# Define the label of the ground-truth which will be provided
label_gt = ['prostate', 'pz', 'cg', 'cap']
# Define the path to the normalization parameters
path_norm = '/data/prostate/pre-processing/lemaitre-2016-nov/norm-objects'

# Generate the different path to be later treated
path_patients_list_dce = []
path_patients_list_gt = []
# Create the generator
id_patient_list = [name for name in os.listdir(path_patients)
                   if os.path.isdir(os.path.join(path_patients, name))]
for id_patient in id_patient_list:
    # Append for the DCE data
    path_patients_list_dce.append(os.path.join(path_patients, id_patient,
                                               path_dce))
    # Append for the GT data - Note that we need a list of gt path
    path_patients_list_gt.append([os.path.join(path_patients, id_patient, gt)
                                  for gt in path_gt])

# Load all the data once. Splitting into training and testing will be done at
# the cross-validation time
data = []
label = []
for idx_pat in range(len(id_patient_list)):
    print 'Read patient {}'.format(id_patient_list[idx_pat])

    # Load the testing data that correspond to the index of the LOPO
    # Create the object for the DCE
    dce_mod = DCEModality()
    dce_mod.read_data_from_path(path_patients_list_dce[idx_pat])
    print 'Read the DCE data for the current patient ...'

    # Create the corresponding ground-truth
    gt_mod = GTModality()
    gt_mod.read_data_from_path(label_gt,
                               path_patients_list_gt[idx_pat])
    print 'Read the GT data for the current patient ...'

    # Load the approproate normalization object
    filename_norm = (id_patient_list[idx_pat].lower().replace(' ', '_') +
                     '_norm.p')
    dce_norm = StandardTimeNormalization.load_from_pickles(
        os.path.join(path_norm, filename_norm))

    dce_mod = dce_norm.normalize(dce_mod)

    # Create the object to extrac data
    dce_ese = EnhancementSignalExtraction(DCEModality())

    # Concatenate the training data
    data.append(dce_ese.transform(dce_mod, gt_mod, label_gt[0]))
    # Extract the corresponding ground-truth for the testing data
    # Get the index corresponding to the ground-truth
    roi_prostate = gt_mod.extract_gt_data('prostate', output_type='index')
    # Get the label of the gt only for the prostate ROI
    gt_cap = gt_mod.extract_gt_data('cap', output_type='data')
    label.append(gt_cap[roi_prostate])
    print 'Data and label extracted for the current patient ...'

n_jobs = 48
config = [{'classifier_str': 'random-forest', 'n_estimators': 100,
           'gs_n_jobs': n_jobs}]

n_comp = [2, 4, 8, 16, 24, 32, 36]

result_config = []
for c in config:

    results_sp = []
    for cp in n_comp:

        result_cv = []
        # Go for LOPO cross-validation
        for idx_lopo_cv in range(len(id_patient_list)):

            # Display some information about the LOPO-CV
            print 'Round #{} of the LOPO-CV'.format(idx_lopo_cv + 1)

            # Get the testing data
            testing_data = data[idx_lopo_cv]
            testing_label = label_binarize(label[idx_lopo_cv], [0, 255])
            print 'Create the testing set ...'

            # Create the training data and label
            training_data = [arr for idx_arr, arr in enumerate(data)
                             if idx_arr != idx_lopo_cv]
            training_label = [arr for idx_arr, arr in enumerate(label)
                              if idx_arr != idx_lopo_cv]
            # Concatenate the data
            training_data = np.vstack(training_data)
            training_label = label_binarize(
                np.hstack(training_label).astype(int),
                [0, 255])
            print 'Create the training set ...'

            # Learn the dicitionary using ICA
            kpca = KernelPCA(n_components=cp, kernel='rbf')
            training_data_projected = kpca.fit_transform(training_data)

            # Project the testing data
            testing_data_projected = kpca.transform(testing_data)

            # Perform the classification for the current cv and the
            # given configuration
            result_cv.append(Classify(training_data_projected, training_label,
                                      testing_data_projected, testing_label,
                                      **c))
        results_sp.append(result_cv)

# Concatenate the results per configuration
result_config.append(results_sp)

# Save the information
path_store = '/data/prostate/results/lemaitre-2016-nov/kpca'
if not os.path.exists(path_store):
    os.makedirs(path_store)
joblib.dump(result_config, os.path.join(path_store,
                                        'results_normalized_ese.pkl'))
