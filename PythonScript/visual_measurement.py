#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Sep 27 16:42:52 2019

@author: James Wu
"""

import cv2
import numpy as np
import dlib
import time
import math
import sys
import time
import socket
import copy

detector = dlib.get_frontal_face_detector()
predictor = dlib.shape_predictor("./data/shape_predictor_68_face_landmarks.dat")
POINTS_NUM_LANDMARK = 68

clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8)) # CLAHE Object (for Adaptive histogram equalization)

boxPoints3D = np.array(([500., 500., 500.],
                         [-500., 500., 500.],
                         [-500., -500., 500.],
                         [500., -500., 500.],
                         [500., 500., -500.],
                         [-500., 500., -500.],
                         [-500., -500., -500.],
                         [500., -500., -500.]))
boxPoints2D = np.zeros((1,1,8,2))
# parameters for mean filter
windowlen_1 = 3
queue3D_points = np.zeros((windowlen_1,POINTS_NUM_LANDMARK,2))

windowlen_2 =5
queue1D = np.zeros(windowlen_2)

# pamameters for kalman filter
XX = 0.01
PP = 0.05


# Smooth filter
def mean_filter_for_landmarks(landmarks_orig):
    for i in range(windowlen_1-1):
        queue3D_points[i,:,:] = queue3D_points[i+1,:,:]
    queue3D_points[windowlen_1-1,:,:] = landmarks_orig
    landmarks = queue3D_points.mean(axis = 0)
    return landmarks

def mean_filter_simple(input):
    for i in range(windowlen_2-1):
        queue1D[i] = queue1D[i+1]
    queue1D[windowlen_2-1] = input
    output = queue1D.mean()
    return output


def kalman_filter_simple(input, Q, R):
    global XX
    global PP
    K = PP / (PP + R)
    XX = XX + K * (input - XX)
    PP = PP - K * PP + Q
    return XX

class KalmanObject:
    def __init__(self, m, Qval, Rval):
        self.K = np.zeros((m,m))
        self.xx = np.zeros(m)
        self.P = np.eye(m)
        self.F = np.eye(m)
        self.B = np.eye(m)
        self.H = np.eye(m)
        self.Q = Qval * np.eye(m)
        self.R = Rval * np.eye(m)

    def kalman_update(self, uu, zz):
        self.xx = self.F.dot(self.xx) + self.B.dot(uu)
        self.P = self.F.dot(self.P).dot(self.F.T) + self.Q
        self.K = self.P.dot(self.H.T).dot( np.linalg.inv(self.H.dot(self.P).dot(self.H.T) + self.R) )
        self.xx = self.xx + self.K.dot(zz - self.H.dot(self.xx))
        self.P = self.P - self.K.dot(self.H).dot(self.P)

# Format convert      
def landmarks_to_np(landmarks, dtype="int"):
    # get number of landmarks
    num = landmarks.num_parts
    
    # initialize the list of (x, y)-coordinates
    coords = np.zeros((num, 2), dtype=dtype)
    
    # loop over the 68 facial landmarks and convert them
    # to a 2-tuple of (x, y)-coordinates
    for i in range(0, num):
        coords[i] = (landmarks.part(i).x, landmarks.part(i).y)
    # return the list of (x, y)-coordinates
    return coords

# Get feature_parameters of facial expressions
def get_feature_parameters(landmarks):
    d00 =np.linalg.norm(landmarks[27]-landmarks[8]) # Length of face (eyebrow to chin)
    d11 =np.linalg.norm(landmarks[0]-landmarks[16]) # width of face
    d_reference = (d00+d11)/2
    # Left eye
    d1 =  np.linalg.norm(landmarks[37]-landmarks[41])
    d2 =  np.linalg.norm(landmarks[38]-landmarks[40])
    # Right eye
    d3 =  np.linalg.norm(landmarks[43]-landmarks[47])
    d4 =  np.linalg.norm(landmarks[44]-landmarks[46])
    # Mouth width
    d5 = np.linalg.norm(landmarks[51]-landmarks[57])
    # Mouth length
    d6 = np.linalg.norm(landmarks[60]-landmarks[64])
    
    leftEyeWid = ((d1+d2)/(2*d_reference) - 0.02)*6
    rightEyewid = ((d3+d4)/(2*d_reference) -0.02)*6
    mouthWid = (d5/d_reference - 0.13)*1.27+0.02
    mouthLen = d6/d_reference

    return leftEyeWid, rightEyewid, mouthWid,mouthLen


# Get largest face
def get_largest_face(dets):
    if len(dets) == 1:
        return 0

    face_areas = [ (det.right()-det.left())*(det.bottom()-det.top()) for det in dets]

    largest_area = face_areas[0]
    largest_index = 0
    for index in range(1, len(dets)):
        if face_areas[index] > largest_area :
            largest_index = index
            largest_area = face_areas[index]

    print("largest_face index is {} in {} faces".format(largest_index, len(dets)))

    return largest_index
    
# Feature points extraction using dlib
def get_image_points(img):                        
    gray = cv2.cvtColor( img, cv2.COLOR_BGR2GRAY )
    gray_eq = clahe.apply(gray) # Adaptive histogram equalization  
    #cv2.imshow("gray",gray)
    #cv2.imshow("gray_eq",gray_eq)
    dets = detector( gray_eq, 0 )

    if 0 == len( dets ):
        print( "ERROR: found no face" )
        return -1, None
    largest_index = get_largest_face(dets)
    face_rectangle = dets[largest_index]

    landmark_shape = predictor(img, face_rectangle)

    return 0, landmark_shape


# Pose estimation: get rotation vector and translation vector           
def get_pose_estimation(img_size, image_points ):
    # 3D model points
#    model_points = np.array([
#                                (0.0, 0.0, 0.0),             # Nose tip
#                                (0.0, -330.0, -65.0),        # Chin
#                                (-225.0, 170.0, -135.0),     # Left eye left corner
#                                (225.0, 170.0, -135.0),      # Right eye right corner
#                                (-150.0, -150.0, -125.0),    # Left Mouth corner
#                                (150.0, -150.0, -125.0)      # Right mouth corner
#                             
#                            ])
    
    model_points = np.array([
                                (0.0, 0.0, 0.0),             # Nose tip
                                (0.0, -330.0, -65.0),        # Chin
                                (-225.0, 170.0, -135.0),     # Left eye left corner
                                (225.0, 170.0, -135.0),      # Right eye right corner
                                (-349.0, 85.0, -300.0),      # Left head corner
                                (349.0, 85.0, -300.0)        # Right head corner
                             
                            ])
    # Camera internals     
    focal_length = img_size[1]
    center = (img_size[1]/2, img_size[0]/2)
    camera_matrix = np.array(
                             [[focal_length, 0, center[0]],
                             [0, focal_length, center[1]],
                             [0, 0, 1]], dtype = "double"
                             )     
    # print("Camera Matrix:\n {}".format(camera_matrix))
     
    dist_coeffs = np.zeros((4,1)) # Assuming no lens distortion
    imagePoints = np.ascontiguousarray(image_points[:,:2]).reshape((6,1,2))
    (success, rotation_vector, translation_vector) = cv2.solvePnP(model_points, imagePoints, camera_matrix, dist_coeffs, flags=cv2.SOLVEPNP_DLS)
    
    ############################
    # rotation_vector[0] = kalman_filter_simple(rotation_vector[0], 0.1, 0.01)
    # rotation_vector[1] = kalman_filter_simple(rotation_vector[1], 0.1, 0.01)
    # rotation_vector[2] = kalman_filter_simple(rotation_vector[2], 0.1, 0.01)

    # print("Rotation Vector:\n {}".format(rotation_vector))
    # print("Translation Vector:\n {}".format(translation_vector))
    return success, rotation_vector, translation_vector, camera_matrix, dist_coeffs

# Convert rotation_vector to quaternion
def get_quaternion(rotation_vector):
        # calculate rotation angles
    theta = cv2.norm(rotation_vector, cv2.NORM_L2)
    # theta = mean_filter_simple(theta)
    
    # transformed to quaterniond
    w = math.cos(theta / 2)
    x = math.sin(theta / 2)*rotation_vector[0][0] / theta
    y = math.sin(theta / 2)*rotation_vector[1][0] / theta
    z = math.sin(theta / 2)*rotation_vector[2][0] / theta
    return round(w,4), round(x,4), round(y,4), round(z,4)

def overlay_transparent(background, overlay, x, y):
    background_width = background.shape[1]
    background_height = background.shape[0]

    if x >= background_width or y >= background_height:
        return background
    
    

    h, w = overlay.shape[0], overlay.shape[1]

    if h + y < 0 or w + x < 0:
        return background

    if x + w > background_width:
        w = background_width - x
        overlay = overlay[:, :w]

    if y + h > background_height:
        h = background_height - y
        overlay = overlay[:h]

    if x < 0:
        w = w + x
        x = 0
        overlay = overlay[:, -w:]
    
    if y < 0:
        h = h + y
        y = 0
        overlay = overlay[-h:, :]

    if overlay.shape[2] < 4:
        overlay = np.concatenate(
            [
                overlay,
                np.ones((overlay.shape[0], overlay.shape[1], 1), dtype = overlay.dtype) * 255
            ],
            axis = 2,
        )

    # overlay_image = overlay[..., :3]
    # mask = overlay[..., 3:] / 255.0

    # background[y:y+h, x:x+w] = (1.0 - mask) * background[y:y+h, x:x+w] + mask * overlay_image
    mask = overlay
    index = overlay[:,:,3] != 0
    index = np.repeat(index[:,:,np.newaxis], axis=2, repeats=3)
    background[y:y+h, x:x+w,:][index] = mask[:,:,:3][index]

    return background


def crop_im(im, padding=0.01):
    """
    Takes cv2 image, im, and padding % as a float, padding,
    and returns cropped image.
    """
    bw = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    rows, cols = bw.shape
    non_empty_columns = np.where(bw.min(axis=0)<255)[0]
    non_empty_rows = np.where(bw.min(axis=1)<255)[0]
    cropBox = (min(non_empty_rows) * (1 - padding),
                min(max(non_empty_rows) * (1 + padding), rows),
                min(non_empty_columns) * (1 - padding),
                min(max(non_empty_columns) * (1 + padding), cols))
    cropped = im[int(cropBox[0]):int(cropBox[1])+1, int(cropBox[2]):int(cropBox[3])+1 , :]

    return cropped


if __name__ == '__main__':

    test_data = [0]
    test_time = [0]
    # Socket Connect
    try:
        client = socket.socket()
        client.connect(('127.0.0.1',1755))
    except:
        print("\nERROR: No socket connection.\n")
        sys.exit(0)
    print("Start\n")
    # initialize kalman object
    KalmanX = KalmanObject(POINTS_NUM_LANDMARK, 1,10) # Tune Q, R to change landmarks_x sensitivity
    KalmanY = KalmanObject(POINTS_NUM_LANDMARK, 1,10) # Tune Q, R to change landmarks_y sensitivity
    uu_ = np.zeros((POINTS_NUM_LANDMARK))
    # initialize PARAMETERS
    landmarks = np.zeros((POINTS_NUM_LANDMARK,2))
    

    # open_time = time.time()
    # cap = cv2.VideoCapture(0)
    cap  = cv2.VideoCapture('./test2.mp4')
    fps = cap.get(cv2.CAP_PROP_FPS)
    size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    # 将预测结果写成视频
    video_writer = cv2.VideoWriter('result.mp4', cv2.VideoWriter_fourcc(*'mp4v'), fps, size)


    while (cap.isOpened()):
        start_time = time.time()
        
        # Read Image
        ret, img = cap.read()
        if ret != True:
            print('read frame failed')
            #continue
            break
        
        
        
        # if size[0] > 700:
        #     h = size[0] / 3
        #     w = size[1] / 3
        #     img = cv2.resize( img, (int( w ), int( h )), interpolation=cv2.INTER_CUBIC )
        #     size = img.shape
        
        
        #img = cv2.normalize(img,dst=None,alpha=350,beta=10,norm_type=cv2.NORM_MINMAX)
        ret, landmark_shape = get_image_points(img)
        if ret != 0:
            print('ERROR: get_image_points failed')
            # continue
            landmark_shape = landmark_shape_last
        landmark_shape_last = landmark_shape
        
        # Compute feature parameters of facial expressions (eyes, mouth)
        landmarks_orig = landmarks_to_np(landmark_shape) # convert format
        
        # Apply kalman filter to landmarks FOR POSE ESTIMATION
        # KalmanX.kalman_update(uu_, landmarks_orig[:,0])
        # KalmanY.kalman_update(uu_, landmarks_orig[:,1])
        # landmarks[:,0] = KalmanX.xx.astype(np.int32)
        # landmarks[:,1] = KalmanY.xx.astype(np.int32)
        landmarks = landmarks_orig

        landmarks = mean_filter_for_landmarks(landmarks) # Apply smooth filter to landmarks FOR POSE ESTIMATION
        leftEyeWid, rightEyewid, mouthWid,mouthLen = get_feature_parameters(landmarks_orig)
        parameters_str = 'leftEyeWid:{}, rightEyewid:{}, mouthWid:{}, mouthLen:{}'.format(leftEyeWid, rightEyewid, mouthWid, mouthLen)
        # print(parameters_str)

        for i in range(68):
            cv2.circle(img, (landmark_shape.part(i).x, landmark_shape.part(i).y),2,(0,255,0), -1, 8)

        # Five feature points for pose estimation
#        image_points = np.vstack((landmarks[30],landmarks[8],landmarks[36],landmarks[45],landmarks[48],landmarks[54]))
        image_points = np.vstack((landmarks[30],landmarks[8],landmarks[36],landmarks[45],landmarks[1],landmarks[15]))
        
        ret, rotation_vector, translation_vector, camera_matrix, dist_coeffs = get_pose_estimation(size, image_points)
        if ret != True:
            print('ERROR: get_pose_estimation failed')
            continue
        used_time = time.time() - start_time
        print("used_time:{} sec".format(round(used_time, 3)))
        
        # Convert rotation_vector to quaternion
        w,x,y,z = get_quaternion(rotation_vector)
        quaternion_str = 'w:{}, x:{}, y:{}, z:{}'.format(w, x, y, z)
        # print(quaternion_str)
        
        # Packing data and transmit to server through Socket
        data = str(translation_vector[0,0])+':'+str(translation_vector[1,0])+':'+str(translation_vector[2,0])+':'+str(w)+':'+str(x)+':'+str(y)+':'+str(z)+':'+str(leftEyeWid)+':'+str(rightEyewid)+':'+str(mouthWid)+':'+str(mouthLen)
        try:
            client.send(data.encode('utf-8'))
        except:
            print("\nSocket connection closed.\n")
            break
        # print(translation_vector)
        #============================================================================
        # For visualization only (below)
        #============================================================================
        
        # Project a 3D point set onto the image plane
        # We use this to draw a bounding box
         
        (nose_end_point2D, jacobian) = cv2.projectPoints(np.array([(0.0, 0.0, 1000)]), rotation_vector, translation_vector, camera_matrix, dist_coeffs)
        
        for i in range(8):
            (boxPoints2D[:,:,i,:], jacobian) = cv2.projectPoints(np.array([boxPoints3D[i]]), rotation_vector, translation_vector, camera_matrix, dist_coeffs)        
        boxPoints2D =  boxPoints2D.astype(int)

        for p in image_points:
            cv2.circle(img, (int(p[0]), int(p[1])), 3, (0,0,255), -1)

        boxset_1 = boxPoints2D[0,0,0:4,:]
        boxset_2 = boxPoints2D[0,0,4:8,:]
        boxset_3 = np.vstack((boxPoints2D[0,0,0,:],boxPoints2D[0,0,4,:]))
        boxset_4 = np.vstack((boxPoints2D[0,0,1,:],boxPoints2D[0,0,5,:]))
        boxset_5 = np.vstack((boxPoints2D[0,0,2,:],boxPoints2D[0,0,6,:]))
        boxset_6 = np.vstack((boxPoints2D[0,0,3,:],boxPoints2D[0,0,7,:]))
        cv2.polylines(img, [boxset_1], True, (255,0,0), 3)
        cv2.polylines(img, [boxset_2], True, (255,0,0), 3)
        cv2.polylines(img, [boxset_3], True, (255,0,0), 3)
        cv2.polylines(img, [boxset_4], True, (255,0,0), 3)
        cv2.polylines(img, [boxset_5], True, (255,0,0), 3)
        cv2.polylines(img, [boxset_6], True, (255,0,0), 3)
        
        p1 = ( int(image_points[0][0]), int(image_points[0][1]))
        p2 = ( int(nose_end_point2D[0][0][0]), int(nose_end_point2D[0][0][1]))
         
        cv2.line(img, p1, p2, (0,255,0), 2)
        cv2.imshow("Output1", img)
        # print(time.asctime( time.localtime(time.time()) ))
        # print(client.recv(1000000))
        fs = client.recv(1000000)
        # print(len(fs))
        _img = cv2.imdecode(np.frombuffer(fs, np.uint8), cv2.IMREAD_UNCHANGED)
        # cv2.imwrite("test.png", _img)
        # _img = crop_im(_img)
        # _img = overlay_transparent(img, _img, int(nose_end_point2D[0][0][0])-int(_img.shape[1]/2), int(nose_end_point2D[0][0][1])-int(img.shape[0]/2))
        mask = crop_im(_img)
        h, w = mask.shape[0], mask.shape[1]
        # new_h = 1.5*2*(image_points[1][1] - image_points[0][1])
        # new_w = w*(new_h/h)
        new_w = 3.0*(image_points[5][0] - image_points[4][0])
        new_h = h*(new_w/w)
        _img = cv2.resize(mask,(int(new_w),int(new_h)),interpolation=cv2.INTER_CUBIC) 

        dx = image_points[0][0] - 0.5*_img.shape[1]
        dy = image_points[0][1] - 0.5*_img.shape[0]

        show_img = overlay_transparent(show_img, _img, int(dx), int(dy)-30)

        cv2.imshow("Output", show_img)
        video_writer.write(show_img)
        # print(nose_end_point2D)
        #============================================================================
        # For visualization only (above)
        #============================================================================

        if (cv2.waitKey(5) & 0xFF)==27:   # Press ESC to quit
            break
    
    client.close() # Socket disconnect
    cap.release()
    video_writer.release()
    cv2.destroyAllWindows()
    
