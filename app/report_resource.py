from flask_restful import fields, Resource, reqparse, request
from baseapp import pagination
from models import ReportUploadModel
from flask import jsonify
import uuid
from controlers import ReportUploadModelDao
from common import login_required
from qcloud_cos import CosConfig
from qcloud_cos import CosS3Client
import sys
import os
import logging

# 正常情况日志级别使用 INFO，需要定位时可以修改为 DEBUG，此时 SDK 会打印和服务端的通信信息
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# 1. 设置用户属性, 包括 secret_id, secret_key, region等。Appid 已在 CosConfig 中移除，请在参数 Bucket 中带上 Appid。Bucket 由 BucketName-Appid 组成
secret_id = os.environ['COS_SECRET_ID']     # 用户的 SecretId，建议使用子账号密钥，授权遵循最小权限指引，降低使用风险。子账号密钥获取可参见 https://cloud.tencent.com/document/product/598/37140
secret_key = os.environ['COS_SECRET_KEY']  # 用户的 SecretKey，建议使用子账号密钥，授权遵循最小权限指引，降低使用风险。子账号密钥获取可参见 https://cloud.tencent.com/document/product/598/37140
region = 'ap-beijing'      # 替换为用户的 region，已创建桶归属的 region 可以在控制台查看，https://console.cloud.tencent.com/cos5/bucket
                           # COS 支持的所有 region 列表参见 https://cloud.tencent.com/document/product/436/6224
token = None               # 如果使用永久密钥不需要填入 token，如果使用临时密钥需要填入，临时密钥生成和使用指引参见 https://cloud.tencent.com/document/product/436/14048
scheme = 'https'           # 指定使用 http/https 协议来访问 COS，默认为 https，可不填

config = CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key, Token=token, Scheme=scheme)
client = CosS3Client(config)

parser = reqparse.RequestParser()
parser.add_argument('num', type=str, required=False, location='args')

upload_fields = {
    'id': fields.Integer,
    'pdf_name': fields.String,
    'pdf_number': fields.String,
    'pdf_origin_name': fields.String
}

allowed_extensions = ['pdf', 'docx']  # 允许上传的文件格式


# pdf 文件列表
class ReportListApi(Resource):
    def get(self):
        args = parser.parse_args()
        arg_num = args['num']
        if arg_num:
            lookfor = gen_lookfor(arg_num)
            return pagination.paginate(ReportUploadModel.query.filter(ReportUploadModel.pdf_number.ilike(lookfor)),
                                       upload_fields)
        else:
            return pagination.paginate(ReportUploadModel,
                                       upload_fields)


def gen_lookfor(needle):
    if '*' in needle or '_' in needle:
        looking_for = needle.replace('_', '__') \
            .replace('*', '%') \
            .replace('?', '_')
    else:
        looking_for = '%{0}%'.format(needle)
    return looking_for


# pdf 上传
class ReportUploadApi(Resource):
    method_decorators = {'post': [login_required]}

    def post(self):
        if 'file' not in request.files:
            print('Please Select File')
            return jsonify(success=False, msg="arg error1")
        f = request.files['file']
        if not allowed_file(f.filename):
            print('Please Select Correct File')
            return jsonify(success=False, msg="arg error2")
        if 'number' not in request.form:
            return jsonify(success=False, msg="arg error3")
        arg_number = request.form['number']
        suffix_name = os.path.splitext(f.filename)[-1][1:]
        gen_file_name = "{}_{}.{}".format(arg_number, uuid.uuid1().hex, suffix_name)
        if f and allowed_file(f.filename):
            response = client.put_object(
                Bucket='sicoss-1253192475',
                Body=f,
                Key=gen_file_name,
                StorageClass='STANDARD',
                EnableMD5=False
            )

            ReportUploadModelDao().updateCreateUploadModel(pdf_name=gen_file_name, pdf_origin_name=f.filename,
                                                           pdf_number=arg_number)
            return jsonify(success=True, msg="upload pdf success{}".format(response['ETag']))


def allowed_file(filename):
    """
    上传文件的格式要求
    :param filename:文件名称
    :return:
    """
    return '.' in filename and \
           filename.rsplit('.')[1].lower() in allowed_extensions


# pdf 删除
class ReportDelApi(Resource):
    method_decorators = {'put': [login_required]}

    def put(self, upload_id):
        model = ReportUploadModelDao().deleteUploadModel(upload_id)
        if model:
            return jsonify(success=True, msg="delete pdf success")
        else:
            return jsonify(success=False, msg="delete pdf fail")
